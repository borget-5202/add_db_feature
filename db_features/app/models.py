# app/models.py
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .db import db
from flask_login import UserMixin
from datetime import datetime


def get_id(self):
    return str(self.id)

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.BigInteger, primary_key=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    username = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="student")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    last_login = db.Column(db.DateTime(timezone=True))

class Game(db.Model):
    __tablename__ = "games"
    id = db.Column(db.BigInteger, primary_key=True)
    slug = db.Column(db.Text, unique=True, nullable=False)      # e.g. 'game24'
    title = db.Column(db.Text, nullable=False)
    subject = db.Column(db.Text, nullable=False, default="math")
    modality = db.Column(db.Text, nullable=False)               # 'cards'|'real_world'
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Text, default="1.0")
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

class Puzzle(db.Model):
    __tablename__ = "puzzles"
    id = db.Column(db.BigInteger, primary_key=True)
    game_id = db.Column(db.BigInteger, db.ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    external_id = db.Column(db.Text)
    title = db.Column(db.Text)
    difficulty = db.Column(db.Text)                             # 'easy'|'medium'|'hard'|'expert'
    content_json = db.Column(JSONB, nullable=False, default={})
    solution_json = db.Column(JSONB)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("game_id", "external_id"),)

class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.BigInteger, primary_key=True)
    session_uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False)  # pass uuid4(), not str
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_id = db.Column(db.BigInteger, db.ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    ended_at = db.Column(db.DateTime(timezone=True))
    completed = db.Column(db.Boolean, nullable=False, default=False)
    device_json = db.Column(JSONB)

class Attempt(db.Model):
    __tablename__ = "attempts"
    id = db.Column(db.BigInteger, primary_key=True)
    session_id = db.Column(db.BigInteger, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    puzzle_id = db.Column(db.BigInteger, db.ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.Text, nullable=False)                  # 'started'|'skipped'|'solved'|'failed'|'revealed'
    started_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    ended_at = db.Column(db.DateTime(timezone=True))
    elapsed_ms = db.Column(db.Integer)
    score = db.Column(db.Integer, default=0)
    detail_json = db.Column(JSONB)

# 🔁 Backwards-compat so old imports keep working:
GameSession = Session

class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.LargeBinary(32), unique=True, nullable=False)  # sha256 digest
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ip = db.Column(db.String(45))   # IPv4/IPv6 text
    user_agent = db.Column(db.Text)

