from .models import db, GameData
import json

def get_game_data(session_id, game_name, data_type, default=None):
    """Get game-specific data for a session"""
    data = UserGameData.query.filter_by(
        session_id=session_id,
        game_name=game_name,
        data_type=data_type
    ).first()
    
    if data and data.data:
        return json.loads(data.data)
    return default

def save_game_data(session_id, game_name, data_type, data_dict):
    """Save game-specific data for a session"""
    data = UserGameData.query.filter_by(
        session_id=session_id,
        game_name=game_name,
        data_type=data_type
    ).first()
    
    if data:
        data.data = json.dumps(data_dict)
    else:
        data = UserGameData(
            session_id=session_id,
            game_name=game_name,
            data_type=data_type,
            data=json.dumps(data_dict)
        )
        db.session.add(data)
    
    db.session.commit()
    return data
