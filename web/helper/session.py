# web/helpers/session.py
import uuid
print("this is core under web")

# ---- Global in-memory state ----
#SESSIONS = {}      # sid -> state dict
#PUZZLES_BY_ID = {} # filled by app.py after loading JSON
#PUZZLES_BY_KEY = {}# values_key "1-4-8-8" -> puzzle

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

