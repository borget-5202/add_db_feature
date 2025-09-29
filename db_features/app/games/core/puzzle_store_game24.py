# app/games/core/puzzle_store_game24.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Callable
import json, random, logging

from flask import current_app
from app.db import db
from app.models import Game, Puzzle

from .game_core import values_key, normalize_level, score_expression_complexity

logger = logging.getLogger(__name__)

SIMPLE_THRESHOLD = 11
HARD_THRESHOLD   = 18

@dataclass(frozen=True)
class G24Puzzle:
    case_id: int
    cards: List[int]
    solutions: List[str]
    level: Optional[str]

class Game24Store:
    """
    Encapsulated, reloadable puzzle store for Game24.
    Lives inside current_app.extensions['game24_store'].
    """
    def __init__(self, cap: Optional[int] = None):
        self.cap = cap
        self.by_id: Dict[int, G24Puzzle] = {}
        self.by_key: Dict[str, G24Puzzle] = {}
        self.pools: Dict[str, List[Tuple[G24Puzzle, List[int], str]]] = {
            "nosol": [], "easy_like": [], "medium": [], "hard_like": [],
        }
        self.loaded_from = None   # 'db' or 'json'

    # -------- public API --------
    def load(self, force: bool = False) -> None:
        if self.by_id and not force:
            return
        puzzles = self._load_from_db()
        self.loaded_from = "db" if puzzles else None
        if not puzzles:
            puzzles = self._load_from_json()
            self.loaded_from = "json"
        self._build_caches(puzzles)

    def pool_report(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self.pools.items()}

    def get_by_id(self, case_id: int) -> Optional[Dict[str, Any]]:
        p = self.by_id.get(int(case_id))
        return self._to_payload(p) if p else None

    def get_by_values(self, values: List[int]) -> Optional[Dict[str, Any]]:
        p = self.by_key.get(values_key(values))
        return self._to_payload(p) if p else None

    def random_pick(
        self,
        level: str,
        recent_keys: List[str],
        eligible: Optional[Callable[[int], bool]] = None
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Return (puzzle_payload, pool_done).
        - Avoids immediate repeats via recent_keys.
        - If 'eligible' is provided, only returns puzzles with eligible(case_id) == True.
        """
        lvl = normalize_level(level)
        pool_name = (
            "nosol"     if lvl in ("challenge", "nosol") else
            "hard_like" if lvl == "hard"                else
            "easy_like" if lvl == "easy"                else
            "medium"
        )
        pool = self.pools.get(pool_name) or self.pools["medium"]
        if not pool:
            return None, False

        # 1) Apply eligibility first (if provided)
        base_candidates = pool
        if eligible is not None:
            base_candidates = [t for t in pool if eligible(int(t[0].case_id))]

        # If nothing is eligible, the pool for this session/level is exhausted
        if not base_candidates:
            return None, True

        # 2) Avoid very recent repeats using your existing values_key scheme
        recent = set(recent_keys[-50:] or [])
        candidates = [t for t in base_candidates if t[2] not in recent]

        # 3) If avoiding repeats empties the set, allow a repeat but signal "done"
        if not candidates:
            choice = random.choice(base_candidates)
            return self._to_payload(choice[0]), True

        # 4) Pick uniformly from remaining candidates
        choice = random.choice(candidates)
        return self._to_payload(choice[0]), False

    # -------- internals --------
    def _to_payload(self, p: G24Puzzle) -> Dict[str, Any]:
        return {
            "case_id": p.case_id,
            "cards": list(p.cards),
            "solutions": list(p.solutions),
            "level": p.level,
        }

    def _load_from_db(self) -> List[G24Puzzle]:
        game = Game.query.filter_by(game_key="game24").first()
        if not game:
            return []
        rows = (Puzzle.query
                .filter_by(game_id=game.game_id, is_active=True)
                .order_by(Puzzle.id.asc())
                .all())
        out: List[G24Puzzle] = []
        for r in rows:
            try:
                cj = r.content_json or {}
                cards = list(map(int, cj.get("cards") or []))
                if len(cards) != 4:
                    continue
                case_id = (
                    int(r.external_id) if r.external_id and str(r.external_id).isdigit()
                    else int(cj.get("case_id"))
                )
                sols = cj.get("solutions") or cj.get("solution") or []
                lvl  = (cj.get("level") or "").strip().lower() or None
                out.append(G24Puzzle(case_id=case_id, cards=cards, solutions=sols, level=lvl))
            except Exception as e:
                logger.warning("skip puzzle id=%s ext=%s: %s", r.id, r.external_id, e)
        return out

    def _load_from_json(self) -> List[G24Puzzle]:
        # answers.json placed at: app/games/game24/static/answers.json
        base = Path(__file__).resolve().parents[2] / "game24" / "static" / "answers.json"
        if not base.exists():
            logger.warning("answers.json missing at %s", base)
            return []
        try:
            data = json.loads(base.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in ("answers","items","data","puzzles"):
                    if k in data and isinstance(data[k], list):
                        data = data[k]; break
                else:
                    data = []
            if not isinstance(data, list):
                return []
            out: List[G24Puzzle] = []
            for row in data:
                cards = list(map(int, row.get("cards") or []))
                if len(cards) != 4: continue
                case_id = int(row.get("case_id"))
                sols    = row.get("solutions") or []
                lvl     = (row.get("level") or "").strip().lower() or None
                out.append(G24Puzzle(case_id=case_id, cards=cards, solutions=sols, level=lvl))
            return out
        except Exception as e:
            logger.exception("load answers.json failed: %s", e)
            return []

    def _build_caches(self, puzzles: List[G24Puzzle]) -> None:
        self.by_id  = {p.case_id: p for p in puzzles}
        self.by_key = {values_key(p.cards): p for p in puzzles}

        nosol, easy, med, hard = [], [], [], []
        med_with_simple, med_with_hard = [], []
        for p in puzzles:
            has_sol = bool(p.solutions)
            vals_key = values_key(p.cards)
            triplet  = (p, p.cards, vals_key)
            lvl = (p.level or "").lower()
            if not has_sol:
                nosol.append(triplet)
            if lvl == "easy" and has_sol:
                easy.append(triplet)
            if lvl == "medium":
                med.append(triplet)
                if has_sol and self._has_simple(p): med_with_simple.append(triplet)
                if has_sol and self._has_hard(p):   med_with_hard.append(triplet)
            if lvl == "hard":
                hard.append(triplet)

        easy_like = easy + med_with_simple
        hard_like = hard + med_with_hard

        self.pools = {
            "nosol": nosol,
            "easy_like": easy_like,
            "medium": med,
            "hard_like": hard_like,
        }

        logger.info("Game24 store loaded (%s): nosol=%d easy=%d medium=%d hard=%d",
                    self.loaded_from or "-", len(nosol), len(easy), len(med), len(hard))
        logger.info("Game24 derived pools: easy_like=%d hard_like=%d",
                    len(easy_like), len(hard_like))

    def _has_simple(self, p: G24Puzzle) -> bool:
        if not p.solutions: return False
        return min(score_expression_complexity(s) for s in p.solutions) <= SIMPLE_THRESHOLD

    def _has_hard(self, p: G24Puzzle) -> bool:
        if not p.solutions: return False
        return max(score_expression_complexity(s) for s in p.solutions) >= HARD_THRESHOLD


# --------- accessors (store lives on current_app) ----------
def get_store(load: bool = True) -> Game24Store:
    ext = getattr(current_app, "extensions", None)
    if ext is None:
        current_app.extensions = {}
        ext = current_app.extensions
    store: Game24Store | None = ext.get("game24_store")
    if store is None:
        store = Game24Store(cap=None)
        ext["game24_store"] = store
    if load:
        store.load(force=False)
    return store

def warmup_store(force: bool = False) -> None:
    get_store(load=False).load(force=force)

