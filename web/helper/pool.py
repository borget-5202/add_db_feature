#web/helpers/pool.py

from shared_state import PUZZLES_BY_ID

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
