# models.py - Revised for multi-game platform
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

# Games catalog table
class Game(db.Model):
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)  # 'game24', 'math_puzzles', etc.
    display_name = db.Column(db.String(100), nullable=False)  # '24 Point Card Game'
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# User sessions with game-specific data
class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.String(128), primary_key=True)  # session_id
    guest_id = db.Column(db.String(128), index=True)
    current_game = db.Column(db.String(100), default='game24')  # references games.name
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to game-specific data
    game_data = db.relationship('UserGameData', backref='session', lazy=True)

# Game-specific data (generic JSON storage)
class UserGameData(db.Model):
    __tablename__ = 'user_game_data'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(128), db.ForeignKey('user_sessions.id'), nullable=False)
    game_name = db.Column(db.String(100), nullable=False)  # 'game24'
    data_type = db.Column(db.String(50), nullable=False)  # 'stats', 'progress', 'settings'
    data = db.Column(db.Text)  # JSON storage
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('session_id', 'game_name', 'data_type', name='unique_game_data'),
    )

# Game content (puzzles, questions, etc.)
class GameContent(db.Model):
    __tablename__ = 'game_content'
    
    id = db.Column(db.Integer, primary_key=True)
    game_name = db.Column(db.String(100), nullable=False)  # 'game24'
    content_id = db.Column(db.String(100), nullable=False)  # 'puzzle_123', 'question_456'
    content_type = db.Column(db.String(50), nullable=False)  # 'puzzle', 'level', 'challenge'
    content_data = db.Column(db.Text)  # JSON storage
    metadata = db.Column(db.Text)  # Additional metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('game_name', 'content_id', name='unique_game_content'),
        db.Index('idx_game_content_type', 'game_name', 'content_type'),
    )

# Teacher/Class management
class TeacherClass(db.Model):
    __tablename__ = 'teacher_classes'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.String(128), index=True)
    class_name = db.Column(db.String(100))
    student_ids = db.Column(db.Text)  # JSON array
    game_assignments = db.Column(db.Text)  # JSON: {game_name: assignment_data}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
