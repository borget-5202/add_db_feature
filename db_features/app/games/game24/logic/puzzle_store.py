from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import json, random, ast, re, logging
from app.models import Game, Puzzle
from app.db import db
from . import game24_utils as gutils

logger = logging.getLogger(__name__)

_initialized = False

# ----------------------------
# Public caches (kept for compatibility with gutils expectations)
# ----------------------------
PUZZLES_BY_ID: Dict[int, Dict[str, Any]] = {}
PUZZLES_BY_KEY: Dict[str, Dict[str, Any]] = {}
POOLS_ADV: Dict[str, List[Tuple[Dict[str, Any], List[int], str]]] = {}

_RANK_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_.])([AaJjQqKkTt])(?![A-Za-z0-9_.])')
_RANK_TOKEN_MAP = {"A":"1","J":"11","Q":"12","K":"13","T":"10"}

def _values_key(cards) -> str:
    return "-".join(map(str, sorted(map(int, cards or []))))

# ---------- Complexity scoring (same spirit as routes) ----------
class _DepthVisitor(ast.NodeVisitor):
    def __init__(self): self.max_depth = 0
    def generic_visit(self, node, depth=0):
        self.max_depth = max(self.max_depth, depth)
        for child in ast.iter_child_nodes(node):
            self.generic_visit(child, depth+1)

def _preprocess_ranks(expr: str) -> str:
    return _RANK_TOKEN_RE.sub(lambda m: _RANK_TOKEN_MAP[m.group(1).upper()], expr)

def score_complexity(expr: str) -> int:
    expr = _preprocess_ranks(expr).replace("^", "**").strip()
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:
        return 999
    ops = {ast.Add:0, ast.Sub:0, ast.Mult:0, ast.Div:0, ast.Pow:0}
    counts = {k: 0 for k in ops}
    node_count = 0
    class V(ast.NodeVisitor):
        def visit_BinOp(self, node):
            nonlocal node_count
            node_count += 1
            op = type(node.op)
            if op in counts: counts[op] += 1
            self.generic_visit(node)
        def visit_UnaryOp(self, node):
            nonlocal node_count; node_count += 1; self.generic_visit(node)
        def visit_Constant(self, node):
            nonlocal node_count; node_count += 1
        def generic_visit(self, node):
            nonlocal node_count; node_count += 1; super().generic_visit(node)
    V().visit(tree)
    dv = _DepthVisitor(); dv.generic_visit(tree)
    score = 0
    score += counts[ast.Add] + counts[ast.Sub] + counts[ast.Mult]
    score += counts[ast.Div] * 2
    score += counts[ast.Pow] * 3
    score += dv.max_depth * 2
    score += max(0, len(expr)//6)
    if counts[ast.Div] >= 2: score += 2
    if counts[ast.Pow] >= 1 and (counts[ast.Div] >= 1 or dv.max_depth >= 4): score += 2
    return int(score)

SIMPLE_THRESHOLD = 11
HARD_THRESHOLD = 18

def _has_solution(p): return bool(p.get("solutions"))
def _has_simple(p) -> bool:
    sols = p.get("solutions") or []
    if not sols: return False
    return min(score_complexity(s) for s in sols) <= SIMPLE_THRESHOLD
def _has_hard(p) -> bool:
    sols = p.get("solutions") or []
    if not sols: return False
    return max(score_complexity(s) for s in sols) >= HARD_THRESHOLD

def _normalize_level(level: Optional[str]) -> str:
    if level is None: return "easy"
    ALIASES = {'0':'easy','easy':'easy','1':'medium','medium':'medium','2':'hard','3':'hard','hard':'hard','4':'challenge','challenge':'challenge','nosol':'nosol'}
    return ALIASES.get(str(level).lower(), str(level).lower())

# ---------- Pooling ----------
def _build_index(puzzles: List[Dict[str, Any]]):
    idx = []
    for p in puzzles:
        vals = list(map(int, p.get('cards') or []))
        idx.append((p, vals, _values_key(vals)))
    return idx

def _preprocess_pool(puzzles: List[Dict[str, Any]]):
    easy_pool, med_pool, hard_pool = [], [], []
    med_pool_with_simple, med_pool_with_hard, nosol_pool = [], [], []
    for (p, vals, key) in _build_index(puzzles):
        lvl = str(p.get("level","")).strip().lower()
        has = _has_solution(p)
        if not has: nosol_pool.append((p, vals, key))
        if lvl == "easy" and has: easy_pool.append((p, vals, key))
        if lvl == "medium":
            med_pool.append((p, vals, key))
            if has and _has_simple(p): med_pool_with_simple.append((p, vals, key))
            if has and _has_hard(p):   med_pool_with_hard.append((p, vals, key))
        if lvl == "hard":  hard_pool.append((p, vals, key))
    easy_like = easy_pool + med_pool_with_simple
    hard_like = hard_pool + med_pool_with_hard
    logger.info("pools: nosol=%d, easy=%d, medium=%d, hard=%d", len(nosol_pool), len(easy_pool), len(med_pool), len(hard_pool))
    logger.info("after sort: easy_like=%d, hard_like=%d", len(easy_like), len(hard_like))
    return {'nosol': nosol_pool, 'easy_like': easy_like, 'medium': med_pool, 'hard_like': hard_pool}

def _pick_from_pool_name(pool_name: str, state: dict):
    pool = POOLS_ADV.get(pool_name, [])
    if not pool: pool = POOLS_ADV.get('medium', [])
    recent = set(state.get('recent_keys', [])[-50:])
    candidates = [t for t in pool if t[2] not in recent] or pool
    choice = random.choice(candidates)
    state.setdefault('recent_keys', []).append(choice[2])
    if len(state['recent_keys']) > 100: state['recent_keys'] = state['recent_keys'][-100:]
    return choice[0]

def random_pick_by_level(level: str, state: dict) -> Dict[str, Any]:
    lvl = _normalize_level(level)
    if lvl in ('challenge','nosol'): return _pick_from_pool_name('nosol', state)
    if lvl == 'hard': return _pick_from_pool_name('hard_like', state)
    if lvl == 'easy': return _pick_from_pool_name('easy_like', state)
    return _pick_from_pool_name('medium', state)

# ---------- Loaders ----------
def _load_from_db() -> List[Dict[str, Any]]:
    game = Game.query.filter_by(slug="game24").first()
    if not game:
        return []
    rows = (Puzzle.query
            .filter_by(game_id=game.id, is_active=True)
            .order_by(Puzzle.id.asc())
            .all())
    puzzles: List[Dict[str, Any]] = []
    for r in rows:
        try:
            cj = r.content_json or {}
            case_id = int(r.external_id) if r.external_id and str(r.external_id).isdigit() else cj.get("case_id")
            cards = list(map(int, cj.get("cards") or []))
            solutions = cj.get("solutions") or cj.get("solution") or []
            level = cj.get("level") or None
            if case_id is None and cards:
                # fabricate stable id from hash of key if needed
                case_id = abs(hash(_values_key(cards))) % 10_000_000
            puzzles.append({
                "case_id": int(case_id),
                "cards": cards,
                "solutions": solutions,
                "level": level
            })
        except Exception as e:
            logger.warning("skip puzzle id=%s ext=%s: %s", r.id, r.external_id, e)
    return puzzles

def _load_from_json() -> List[Dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "static" / "answers.json"
    if not path.exists():
        logger.warning("answers.json not found at %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k in ("answers","items","data","puzzles"):
                if k in data and isinstance(data[k], list):
                    data = data[k]; break
            else:
                data = []
        if not isinstance(data, list):
            logger.warning("Invalid answers.json format")
            return []
        return data
    except Exception as e:
        logger.exception("Failed loading answers.json: %s", e)
        return []

def _rebuild_caches(puzzles: List[Dict[str, Any]]):
    global PUZZLES_BY_ID, PUZZLES_BY_KEY, POOLS_ADV
    PUZZLES_BY_ID = {int(p.get("case_id")): p for p in puzzles if "case_id" in p}
    PUZZLES_BY_KEY = {_values_key(p.get("cards") or []): p for p in puzzles}
    POOLS_ADV = _preprocess_pool(puzzles)
    # keep gutils in sync (legacy callers)
    gutils.PUZZLES_BY_ID = PUZZLES_BY_ID
    gutils.PUZZLES_BY_KEY = PUZZLES_BY_KEY

def init_store(force: bool = False):
    """Load from DB if available; else fallback to JSON. Build caches & pools
    Idempotent unless force=True."""
    global _initialized
    if _initialized and not force:
        logger.debug("puzzle_store: already initialized; skip")
        return
    puzzles = _load_from_db()
    src = "db"
    if not puzzles:
        puzzles = _load_from_json()
        src = "json"
    _rebuild_caches(puzzles)
    logger.info("puzzle_store initialized from %s: %d puzzles", src, len(puzzles))
    _initialized = True

# ---------- Lookup helpers ----------
def get_puzzle_by_id(case_id: int) -> Optional[Dict[str, Any]]:
    return PUZZLES_BY_ID.get(int(case_id))

def get_puzzle_by_values(values: List[int]) -> Optional[Dict[str, Any]]:
    return PUZZLES_BY_KEY.get(_values_key(values))

