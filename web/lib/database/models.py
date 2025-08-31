from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Game(db.Model):
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    id = db.Column(db.String(128), primary_key=True)
    guest_id = db.Column(db.String(128), index=True)
    current_game = db.Column(db.String(100), default='game24')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserGameData(db.Model):
    __tablename__ = 'user_game_data'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(128), db.ForeignKey('user_sessions.id'), nullable=False)
    game_name = db.Column(db.String(100), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
