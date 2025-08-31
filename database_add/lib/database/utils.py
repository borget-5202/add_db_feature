from . import db

def init_db(app):
    """Initialize database with default data"""
    with app.app_context():
        db.create_all()
        
        # Add default games if they don't exist
        from .models import Game
        
        default_games = [
            Game(name='24-Point Puzzle', description='Mathematical card game where players use four numbers to make 24'),
            # Add more games here as you develop them
        ]
        
        for game_data in default_games:
            if not Game.query.filter_by(name=game_data.name).first():
                db.session.add(game_data)
        
        db.session.commit()

def clear_db():
    """Clear all database data (for testing)"""
    meta = db.metadata
    for table in reversed(meta.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
