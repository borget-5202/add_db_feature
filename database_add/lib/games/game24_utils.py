from lib.database.helpers import get_game_data, save_game_data
import uuid
import json
from pathlib import Path
import logging

# ---- Global in-memory state ----
ALL_PUZZLES = None
POOLS_ADV = None
default_state = None
SESSIONS = {}      # sid -> state dict
PUZZLES_BY_ID = {} # filled by app.py after loading JSON
PUZZLES_BY_KEY = {}# values_key "1-4-8-8" -> puzzle

# Add ASSETS_DIR definition
BASE_DIR = Path(__file__).parent.parent.parent  # Adjust based on your structure
ASSETS_DIR = BASE_DIR / "web" / "static" / "games" / "game24" / "images" / "cards"

# Configure logging
logger = logging.getLogger(__name__)

# Answers path
ANSWERS_PATH = BASE_DIR / "web" / "static" / "games" / "game24" / "data" / "answers.json"

def default_state():
    return {
        'stats': {
            # classic totals
            'played': 0,
            'solved': 0,
            'revealed': 0,
            'skipped': 0,
            'by_level': {},  # level -> {played, solved}

            # NEW: action-level counters (all modes)
            'help_single': 0,     # /api/help (all==false)
            'help_all': 0,        # /api/help (all==true)
            'answer_attempts': 0, # /api/check (any input, including "no solution")
            'answer_correct': 0,  # attempts that were correct
            'answer_wrong': 0,    # attempts that were wrong/invalid
            'deal_swaps': 0,      # user hit Deal, then Deal again without any interaction in between
        },

        # runtime flags
        'help_disabled': False,
        'current_case_id': None,
        'current_effective_level': None,
        'recent_keys': [],        # last N dealt to avoid repeats
        'hand_interacted': False, # first interaction flag for current hand

        # competition/pools
        # 'competition_ends_at': float epoch
        # 'pool' added lazily by _pool()
    }

# ----- session & identity helpers -----
def get_or_create_session_id(req):
    """
    Session key = cookie + optional per-tab client_id (query/body/header).
    """
    base = req.cookies.get('session_id') or str(uuid.uuid4())

    client = None
    try:
        client = req.args.get('client_id')
    except Exception:
        client = None
    if not client and req.is_json:
        j = req.get_json(silent=True) or {}
        client = j.get('client_id')
    if not client:
        client = req.headers.get('X-Client-Session')

    if client:
        return f"{base}:{str(client)[:64]}"
    return base

def get_guest_id(req):
    gid = None
    try:
        gid = req.args.get('guest_id')
    except Exception:
        pass
    if not gid and req.is_json:
        j = req.get_json(silent=True) or {}
        gid = j.get('guest_id')
    if not gid:
        gid = req.headers.get('X-Guest-Id')
    return str(gid)[:64] if gid else None

# ----- pool helpers (custom / competition) -----
def _pool(state):
    return state.setdefault('pool', {
        'mode': None,     # 'custom' | 'competition' | None
        'ids': [],        # [case_id, ...]
        'index': 0,       # next index to serve (sequential)
        'status': {},     # str(cid) -> {'status': 'unseen'|'shown'|'good'|'revealed'|'skipped'|'attempted', 'attempts': int}
        'score': {},      # str(cid) -> 0 or 1   (0 at start; set to 1 only on correct answer)
        'done': False,    # all shown once
    })

def _mark_case_status(state, case_id, action):
    p = _pool(state)
    key = str(case_id)
    entry = p['status'].setdefault(key, {'status': 'unseen', 'attempts': 0})

    if action == 'shown':
        if entry['status'] == 'unseen':
            entry['status'] = 'shown'
    elif action == 'attempt':
        entry['attempts'] += 1
        if entry['status'] in ('unseen', 'shown'):
            entry['status'] = 'attempted'
    elif action == 'revealed':
        if entry['status'] != 'good':
            entry['status'] = 'revealed'
    elif action == 'skipped':
        if entry['status'] != 'good':
            entry['status'] = 'skipped'
    elif action == 'good':
        entry['status'] = 'good'

def _set_case_solved(state, case_id):
    """Binary score: flip to 1 only on correct answer."""
    p = _pool(state)
    p['score'][str(case_id)] = 1

def _pool_report(state):
    """Legacy detailed report (status/attempts per case)."""
    rows = []
    p = _pool(state)
    for cid in p['ids']:
        puz = PUZZLES_BY_ID.get(int(cid))
        level = puz.get('level') if puz else None
        e = p['status'].get(str(cid), {'status':'unseen','attempts':0})
        rows.append({'case_id': cid, 'level': level, 'status': e['status'], 'attempts': e['attempts']})
    return rows

def _pool_score(state):
    """Compact 0/1 map and unfinished list."""
    p = _pool(state)
    score = {str(cid): int(p['score'].get(str(cid), 0)) for cid in p['ids']}
    unfinished = [int(cid) for cid, v in score.items() if v == 0]
    return score, unfinished

# ----- stats helpers -----
def bump_played_once(state, level_for_stats: str):
    """Call on FIRST interaction (check/help/skip) of a hand."""
    if not state.get('hand_interacted'):
        st = state['stats']
        st['played'] += 1
        by = st['by_level'].setdefault(level_for_stats, {'played': 0, 'solved': 0})
        by['played'] += 1
        state['hand_interacted'] = True

def bump_solved(state, level_for_stats: str):
    st = state['stats']
    st['solved'] += 1
    by = st['by_level'].setdefault(level_for_stats, {'played': 0, 'solved': 0})
    by['solved'] += 1

def bump_revealed(state):
    state['stats']['revealed'] += 1

def bump_skipped(state):
    state['stats']['skipped'] += 1

# NEW counters
def bump_help(state, all=False):
    if all:
        state['stats']['help_all'] += 1
    else:
        state['stats']['help_single'] += 1

def bump_attempt(state, correct: bool):
    st = state['stats']
    st['answer_attempts'] += 1
    if correct:
        st['answer_correct'] += 1
    else:
        st['answer_wrong'] += 1

def bump_deal_swap(state):
    state['stats']['deal_swaps'] += 1

def get_game24_stats(session_id):
    return get_game_data(session_id, 'game24', 'stats', {
        'played': 0, 'solved': 0, 'revealed': 0, 'skipped': 0,
        'by_level': {}, 'help_single': 0, 'help_all': 0,
        'answer_attempts': 0, 'answer_correct': 0, 'answer_wrong': 0,
        'deal_swaps': 0
    })

def save_game24_stats(session_id, stats):
    save_game_data(session_id, 'game24', 'stats', stats)


def get_pools_adv():
    """Get the pre-processed pools, initializing if necessary"""
    global POOLS_ADV, ALL_PUZZLES
    if POOLS_ADV is None:
        init_shared_state()
    return POOLS_ADV

def init_shared_state():
    """Initialize the shared state - call this once when app starts"""
    global ALL_PUZZLES, PUZZLES_BY_ID, PUZZLES_BY_KEY, POOLS_ADV

    logger.info("Initializing shared state...")
    logger.info("Answers path: %s", ANSWERS_PATH)
    logger.info("Assets path: %s", ASSETS_DIR)

    # Verify paths exist
    if not ANSWERS_PATH.exists():
        logger.error("❌ Answers file not found: %s", ANSWERS_PATH)
        raise FileNotFoundError(f"Answers file not found: {ANSWERS_PATH}")

    if not ASSETS_DIR.exists():
        logger.warning("Assets directory not found: %s", ASSETS_DIR)

    # Load answers.json
    with open(ANSWERS_PATH, encoding='utf-8') as f:
        ALL_PUZZLES = json.load(f)
    logger.info(f"{len(ALL_PUZZLES)} puzzles ")

    try:
        # Load answers.json
        logger.info("reload Loading answers.json...")
        with open(ANSWERS_PATH, encoding='utf-8') as f:
            ALL_PUZZLES = json.load(f)
        logger.info("✓ Successfully loaded answers.json")
        
        # Debug: print first few items
        logger.info("First 3 puzzles: %s", ALL_PUZZLES[:3] if ALL_PUZZLES else "EMPTY")
        logger.info("Total puzzles loaded: %d", len(ALL_PUZZLES) if ALL_PUZZLES else 0)

    except Exception as e:
        logger.error("❌ Error loading answers.json: %s", e)
        raise

    # Create lookups
    PUZZLES_BY_ID = {int(p['case_id']): p for p in ALL_PUZZLES}
    PUZZLES_BY_KEY = {_values_key(p['cards']): p for p in ALL_PUZZLES}

    # Pre-process pools
    POOLS_ADV = pre_process_pool(ALL_PUZZLES)

    logger.info("✓ Loaded %d puzzles", len(ALL_PUZZLES))
    logger.info("✓ Pre-processed into difficulty pools")

# ===== HELPER FUNCTIONS =====
def _values_key(cards):
    """Convert cards to sorted key string"""
    return "-".join(map(str, sorted(map(int, cards or []))))

def _build_index(puzzles):
    """Build index for pool processing"""
    idx = []
    for p in puzzles:
        vals = list(map(int, p.get('cards') or []))
        key = _values_key(vals)
        idx.append((p, vals, key))
    return idx

def has_solution(p):
    """Check if puzzle has solutions"""
    return bool(p.get('solutions'))

def puzzle_has_simple_solution(p):
    """Check if puzzle has simple solution (no ^ operator)"""
    for s in (p.get('solutions') or []):
        if '^' not in s:
            return True
    return False

def puzzle_has_hard_solution(p):
    """Check if puzzle has hard solution (with ^ operator)"""
    for s in (p.get('solutions') or []):
        if '^' in s:
            return True
    return False

def pre_process_pool(puzzles):
    """Pre-process puzzles into difficulty pools"""
    logger.debug("Pre-processing puzzles into difficulty pools")

    easy_pool = []
    med_pool_with_simple = []
    med_pool = []
    hard_pool = []
    med_pool_with_hard = []
    nosol_pool = []

    for (p, vals, key) in _build_index(puzzles):
        lvl = str(p.get("level","")).strip().lower()
        _has = has_solution(p)

        if not _has:
            nosol_pool.append((p, vals, key))
        elif lvl == "easy":
            easy_pool.append((p, vals, key))
        elif lvl == "medium":
            med_pool.append((p, vals, key))
            if puzzle_has_simple_solution(p):
                med_pool_with_simple.append((p, vals, key))
            if puzzle_has_hard_solution(p):
                med_pool_with_hard.append((p, vals, key))
        elif lvl == "hard":
            hard_pool.append((p, vals, key))

    easy_like = easy_pool + med_pool_with_simple
    hard_like = hard_pool + med_pool_with_hard

    logger.debug(
        "Processed puzzles: nosol=%d, easy_like=%d, medium=%d, hard_like=%d",
        len(nosol_pool), len(easy_like), len(med_pool), len(hard_like)
    )

    return {
        'nosol': nosol_pool,
        'easy': easy_like,
        'medium': med_pool,
        'hard': hard_like,
    }

# lib/games/game24_utils.py - ADD THIS FUNCTION
def validate_solution(puzzle_id, user_solution):
    """Validate if the solution produces 24"""
    # Placeholder - implement your actual validation logic
    try:
        # Basic safety check before eval
        if not is_safe_expression(user_solution):
            return False

        # Evaluate the expression
        result = eval(user_solution)
        return abs(result - 24) < 0.001  # Allow for floating point precision

    except:
        return False

def is_safe_expression(expr):
    """Basic safety check for mathematical expressions"""
    import re
    # Allow only numbers, operators, and parentheses
    safe_pattern = r'^[0-9+\-*/().\s]+$'
    return bool(re.match(safe_pattern, expr))


__all__ = [
    'SESSIONS', 'PUZZLES_BY_ID', 'PUZZLES_BY_KEY', 'default_state', 'ANSWERS_PATH', 
    'ASSETS_DIR', 'init_shared_state', 'get_pools_adv', 'ALL_PUZZLES', 'POOLS_ADV'
]
