# models.py - Revised for multi-game platform
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
from . import db

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = {"schema": "app"}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')
    grade_level = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    profile_data = db.Column(db.JSON)  # Changed from db.Text to db.JSON

    # ADD THESE NEW FIELDS FOR GAME SCORES
    game24_total_score = db.Column(db.Integer, default=0)
    game24_total_attempts = db.Column(db.Integer, default=0)
    game24_correct_attempts = db.Column(db.Integer, default=0)
    game24_last_played = db.Column(db.DateTime)

    game24_total_puzzles = db.Column(db.Integer, default=0)
    game24_correct_puzzles = db.Column(db.Integer, default=0)
    game24_max_streak = db.Column(db.Integer, default=0)

# Games catalog table
class Game(db.Model):
    __tablename__ = 'games'
    __table_args__ = {"schema": "app"}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)  # 'game24', 'math_puzzles', etc.
    display_name = db.Column(db.String(100), nullable=False)  # '24 Point Card Game'
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    difficulty_range = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    version = db.Column(db.String(20), default='1.0')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    game_metadata = db.Column(db.JSON)  # Changed from db.Text to db.JSON

class GameData(db.Model):
    __tablename__ = 'user_game_data'
    __table_args__ = (
        db.UniqueConstraint('session_id', 'game_name', 'data_type', name='unique_game_data'),
        {"schema": "app"},
    )

    id = db.Column(db.Integer, primary_key=True)
    # FIX THIS LINE - add 'app.' prefix:
    session_id = db.Column(db.String(128), db.ForeignKey('app.game_sessions.id'), nullable=False)
    game_name = db.Column(db.String(100), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Game content (puzzles, questions, etc.)
class GameContent(db.Model):
    __tablename__ = 'game_content'
    __table_args__ = (
        db.UniqueConstraint('game_name', 'content_id', name='unique_game_content'),
        db.Index('idx_game_content_type', 'game_name', 'content_type'),
         {"schema": "app"},
    )
    
    id = db.Column(db.Integer, primary_key=True)
    game_name = db.Column(db.String(100), nullable=False)  # 'game24'
    content_id = db.Column(db.String(100), nullable=False)  # 'puzzle_123', 'question_456'
    content_type = db.Column(db.String(50), nullable=False)  # 'puzzle', 'level', 'challenge'
    content_data = db.Column(db.Text)  # JSON storage
    content_metadata = db.Column(db.Text)  # Additional metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    

# Teacher/Class management
class TeacherClass(db.Model):
    __tablename__ = 'teacher_classes'
    __table_args__ = {"schema": "app"}
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.String(128), index=True)
    class_name = db.Column(db.String(100))
    student_ids = db.Column(db.Text)  # JSON array
    game_assignments = db.Column(db.Text)  # JSON: {game_name: assignment_data}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GameSession(db.Model):
    __tablename__ = 'game_sessions'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'game_id', 'session_uuid', name='unique_user_game_session'),
         {"schema": "app"},
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('app.games.id'))
    session_uuid = db.Column(db.String(36), unique=True, nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    score = db.Column(db.Integer, default=0)
    duration = db.Column(db.Integer)
    completed = db.Column(db.Boolean, default=False)
    device_info = db.Column(db.JSON)
    
    # Add relationships
    user = db.relationship('User', backref='game_sessions')
    game = db.relationship('Game', backref='sessions')
    # Add relationship to GameData
    game_data = db.relationship('GameData', backref='session', lazy=True)

class GameProgress(db.Model):
    __tablename__ = 'game_progress'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'game_id', 'puzzle_id', name='unique_user_game_puzzle'),
        {'schema': 'app'},
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('app.game_sessions.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('app.games.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    level_name = db.Column(db.String(50), nullable=False)
    puzzle_id = db.Column(db.String(100))
    attempts = db.Column(db.Integer, default=0)
    successes = db.Column(db.Integer, default=0)
    time_taken = db.Column(db.Integer)
    hints_used = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime)
    
