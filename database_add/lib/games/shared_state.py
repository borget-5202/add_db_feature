#/web/shared_state.py

"""Shared global state for the application"""
import json
from pathlib import Path
import logging

# Set up logging
logger = logging.getLogger(__name__)

# ===== GLOBAL PATHS =====
STATIC_DIR = Path(__file__).parent / 'static'
ASSETS_DIR = STATIC_DIR / 'assets' / 'images'
ANSWERS_PATH = STATIC_DIR / 'answers.json'

# ===== PUZZLE DATA =====
ALL_PUZZLES = None
PUZZLES_BY_ID = {}
PUZZLES_BY_KEY = {}
POOLS_ADV = {}

# ===== SESSIONS =====
SESSIONS = {}

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
        'easy_like': easy_like,
        'medium': med_pool,
        'hard_like': hard_like,
    }

def default_state():
    """Default session state"""
    return {
        'stats': {
            'played': 0, 'solved': 0, 'revealed': 0, 'skipped': 0,
            'by_level': {}, 'help_single': 0, 'help_all': 0,
            'answer_attempts': 0, 'answer_correct': 0, 'answer_wrong': 0,
            'deal_swaps': 0
        },
        'help_disabled': False,
        'current_case_id': None,
        'current_effective_level': None,
        'recent_keys': [],
        'hand_interacted': False
    }

def init_shared_state():
    """Initialize the shared state - call this once when app starts"""
    global ALL_PUZZLES, PUZZLES_BY_ID, PUZZLES_BY_KEY, POOLS_ADV
    
    logger.info("Initializing shared state...")
    logger.info("Answers path: %s", ANSWERS_PATH)
    logger.info("Assets path: %s", ASSETS_DIR)
    
    # Verify paths exist
    if not ANSWERS_PATH.exists():
        raise FileNotFoundError(f"Answers file not found: {ANSWERS_PATH}")
    
    if not ASSETS_DIR.exists():
        logger.warning("Assets directory not found: %s", ASSETS_DIR)
    
    # Load answers.json
    with open(ANSWERS_PATH, encoding='utf-8') as f:
        ALL_PUZZLES = json.load(f)
    
    # Create lookups
    PUZZLES_BY_ID = {int(p['case_id']): p for p in ALL_PUZZLES}
    PUZZLES_BY_KEY = {_values_key(p['cards']): p for p in ALL_PUZZLES}
    
    # Pre-process pools
    POOLS_ADV = pre_process_pool(ALL_PUZZLES)
    
    logger.info("✓ Loaded %d puzzles", len(ALL_PUZZLES))
    logger.info("✓ Pre-processed into difficulty pools")
