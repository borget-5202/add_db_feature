from .models import User, Game, GameSession, UserAchievement
from ..games.game24_models import Game24Stats
from datetime import datetime, timedelta

def get_user_by_id(user_id):
    return User.query.get(user_id)

def get_user_by_username(username):
    return User.query.filter_by(username=username).first()

def get_user_by_email(email):
    return User.query.filter_by(email=email).first()

def get_game_by_name(game_name):
    return Game.query.filter_by(name=game_name).first()

def get_active_session(user_id, game_id):
    return GameSession.query.filter_by(
        user_id=user_id, 
        game_id=game_id,
        completed=False
    ).first()

def create_game_session(user_id, game_id):
    session = GameSession(user_id=user_id, game_id=game_id)
    db.session.add(session)
    db.session.commit()
    return session

def get_user_stats(user_id, game_name):
    game = get_game_by_name(game_name)
    if not game:
        return None
    
    stats = Game24Stats.query.join(GameSession).filter(
        GameSession.user_id == user_id,
        GameSession.game_id == game.id
    ).first()
    
    return stats

def get_leaderboard(game_name, limit=10):
    game = get_game_by_name(game_name)
    if not game:
        return []
    
    return Game24Stats.query.join(GameSession).filter(
        GameSession.game_id == game.id,
        Game24Stats.puzzles_solved > 0
    ).order_by(
        Game24Stats.puzzles_solved.desc(),
        Game24Stats.average_solve_time.asc()
    ).limit(limit).all()
