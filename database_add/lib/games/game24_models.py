from lib.database import db
from datetime import datetime

class Game24Stats(db.Model):
    __tablename__ = 'game24_stats'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)  # Added primary key
    session_id = db.Column(db.Integer, db.ForeignKey('app.game_sessions.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    puzzles_attempted = db.Column(db.Integer, default=0)
    puzzles_solved = db.Column(db.Integer, default=0)
    average_solve_time = db.Column(db.Numeric)  # Changed from Float to Numeric
    max_streak = db.Column(db.Integer, default=0)
    total_time_played = db.Column(db.Integer, default=0)  # Changed from Float to Integer
    difficulty_breakdown = db.Column(db.JSON)  # Changed from db.Text to db.JSON
    common_operations = db.Column(db.JSON)  # Changed from db.Text to db.JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Update relationship to match actual table
    session = db.relationship('GameSession', backref=db.backref('game24_stats', uselist=False))
