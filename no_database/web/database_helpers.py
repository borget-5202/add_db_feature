# database_helpers.py
def get_game_data(session_id, game_name, data_type, default=None):
    data = UserGameData.query.filter_by(
        session_id=session_id, 
        game_name=game_name, 
        data_type=data_type
    ).first()
    
    if data:
        return json.loads(data.data)
    return default or {}

def save_game_data(session_id, game_name, data_type, data_dict):
    existing = UserGameData.query.filter_by(
        session_id=session_id, 
        game_name=game_name, 
        data_type=data_type
    ).first()
    
    if existing:
        existing.data = json.dumps(data_dict)
        existing.updated_at = datetime.utcnow()
    else:
        new_data = UserGameData(
            session_id=session_id,
            game_name=game_name,
            data_type=data_type,
            data=json.dumps(data_dict)
        )
        db.session.add(new_data)
    
    db.session.commit()

# Game24 specific helpers
def get_game24_stats(session_id):
    return get_game_data(session_id, 'game24', 'stats', {
        'played': 0, 'solved': 0, 'revealed': 0, 'skipped': 0,
        'by_level': {}, 'help_single': 0, 'help_all': 0,
        'answer_attempts': 0, 'answer_correct': 0, 'answer_wrong': 0,
        'deal_swaps': 0
    })

def save_game24_stats(session_id, stats):
    save_game_data(session_id, 'game24', 'stats', stats)

def get_game24_pool(session_id):
    return get_game_data(session_id, 'game24', 'pool', {
        'mode': None, 'ids': [], 'index': 0, 
        'status': {}, 'score': {}, 'done': False
    })

def save_game24_pool(session_id, pool_data):
    save_game_data(session_id, 'game24', 'pool', pool_data)
