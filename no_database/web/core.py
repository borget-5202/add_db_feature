# web/core.py
import uuid
print("this is core under web")

# ---- Global in-memory state ----
SESSIONS = {}      # sid -> state dict
PUZZLES_BY_ID = {} # filled by app.py after loading JSON
PUZZLES_BY_KEY = {}# values_key "1-4-8-8" -> puzzle


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

