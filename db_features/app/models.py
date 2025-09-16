# app/models.py
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from .db import db
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy.ext.mutable import MutableDict

puzzle_difficulty = PGEnum(
    'intro','easy','medium','hard','challenge','expert',
    name='puzzle_difficulty', schema='app', create_type=False
)

class GameItem(db.Model):
    __tablename__  = "game_items"
    __table_args__ = {"schema": "app"}

    id            = db.Column(db.BigInteger, primary_key=True)
    game_id       = db.Column(db.BigInteger, db.ForeignKey("app.games.game_id"), nullable=False)
    external_id   = db.Column(db.Text)      # unique within a game (with game_id)
    title         = db.Column(db.Text)
    difficulty    = db.Column(puzzle_difficulty)
    content_json  = db.Column(JSONB, nullable=False, default=dict)
    solution_json = db.Column(JSONB)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)
    source        = db.Column(db.Text)
    content_sha1  = db.Column(db.Text)
    meta      = db.Column("metadata", JSONB, nullable=False, server_default=db.text("'{}'::jsonb"))
    created_at    = db.Column(db.DateTime(timezone=True), server_default=db.text("now()"))

    __table_args__ = (
        db.UniqueConstraint("game_id", "external_id", name="uq_game_items_game_ext"),
        {"schema": "app"},
    )


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
    meta = db.Column("metadata", JSONB, nullable=False,
                     server_default=db.text("'{}'::jsonb"))

class Game(db.Model):
    __tablename__ = "games"
    __table_args__ = {"schema": "app"}
    game_id = db.Column("game_id", db.BigInteger, primary_key=True)
    slug = db.Column(db.Text, unique=True, nullable=False)      # e.g. 'game24'
    title = db.Column(db.Text, nullable=False)
    subject = db.Column(db.Text, nullable=False, default="math")
    modality = db.Column(db.Text, nullable=False)               # 'cards'|'real_world'
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Text, default="1.0")
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    meta = db.Column("metadata", JSONB, nullable=False, server_default=db.text("'{}'::jsonb"))
    update_dt = db.Column(db.DateTime(timezone=True))

class Puzzle(db.Model):
    __tablename__ = "game24_puzzles"
    id = db.Column(db.BigInteger, primary_key=True)
    game_id = db.Column(db.BigInteger)
    #game_id = db.Column(db.BigInteger, db.ForeignKey("games.game_id", ondelete="CASCADE"), nullable=False)
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
    game_id = db.Column(db.BigInteger, db.ForeignKey("games.game_id", ondelete="CASCADE"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    ended_at = db.Column(db.DateTime(timezone=True))
    completed = db.Column(db.Boolean, nullable=False, default=False)
    device_json = db.Column(JSONB)
    meta = db.Column('metadata', MutableDict.as_mutable(JSONB),
                 nullable=False, server_default=db.text("'{}'::jsonb"))

class Attempt(db.Model):
    __tablename__ = "attempts"
    id = db.Column(db.BigInteger, primary_key=True)
    session_id = db.Column(db.BigInteger, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    puzzle_id = db.Column(db.BigInteger, db.ForeignKey("app.game24_puzzles.id", ondelete="CASCADE"), nullable=False)
    puzzle = db.relationship("Puzzle", primaryjoin="Attempt.puzzle_id==Puzzle.id", foreign_keys=[puzzle_id])
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

# app/models.py (add below your existing imports)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func

# -------------------------
# Organizations
# -------------------------
class Organization(db.Model):
    __tablename__  = "organizations"
    __table_args__ = {"schema": "app"}

    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    slug = db.Column(db.String(120), nullable=True, unique=True)

    # JSONB backing column is named "metadata" in DB; Python attribute is "meta"
    meta = db.Column("metadata", JSONB, nullable=False,
                     server_default=db.text("'{}'::jsonb"))

    created_at = db.Column(db.DateTime(timezone=True),
                           nullable=False,
                           server_default=func.now())

    # relationships
    classrooms = db.relationship("Classroom", back_populates="organization", lazy="dynamic")

    def __repr__(self):
        return f"<Organization id={self.id} name={self.name!r}>"


# -------------------------
# Classrooms
# -------------------------
class Classroom(db.Model):
    __tablename__  = "classrooms"
    __table_args__ = {"schema": "app"}

    id               = db.Column(db.Integer, primary_key=True)
    organization_id  = db.Column(db.Integer, db.ForeignKey("app.organizations.id"), nullable=True)
    name             = db.Column(db.String(120), nullable=False)
    code             = db.Column(db.String(32), nullable=True, unique=True)   # join code (optional)
    grade_level      = db.Column(db.String(32), nullable=True)                # e.g., "K", "1", "2", ..., "8"

    meta = db.Column("metadata", JSONB, nullable=False,
                     server_default=db.text("'{}'::jsonb"))

    created_at = db.Column(db.DateTime(timezone=True),
                           nullable=False,
                           server_default=func.now())

    # relationships
    organization = db.relationship("Organization", back_populates="classrooms")
    enrollments  = db.relationship("Enrollment", back_populates="classroom", lazy="dynamic")

    def __repr__(self):
        return f"<Classroom id={self.id} name={self.name!r}>"


# -------------------------
# Enrollments (user <-> classroom)
# -------------------------
class Enrollment(db.Model):
    __tablename__  = "enrollments"
    __table_args__ = (
        # prevent duplicates (same user in same classroom twice)
        db.UniqueConstraint("user_id", "classroom_id", name="uq_enroll_user_class"),
        {"schema": "app"},
    )

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("app.users.id"), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey("app.classrooms.id"), nullable=False)

    # role = 'student' | 'teacher' | 'assistant'
    role    = db.Column(db.String(20), nullable=False, server_default="student")
    status  = db.Column(db.String(20), nullable=False, server_default="active")  # 'active' | 'invited' | 'removed'

    meta = db.Column("metadata", JSONB, nullable=False,
                     server_default=db.text("'{}'::jsonb"))

    created_at = db.Column(db.DateTime(timezone=True),
                           nullable=False,
                           server_default=func.now())

    # relationships
    classroom = db.relationship("Classroom", back_populates="enrollments")
    user      = db.relationship("User", backref=db.backref("enrollments", lazy="dynamic"))

    def __repr__(self):
        return f"<Enrollment user_id={self.user_id} classroom_id={self.classroom_id} role={self.role}>"


# -------------------------
# Events (audit/analytics trail)
# -------------------------
class Event(db.Model):
    __tablename__  = "events"
    __table_args__ = {"schema": "app"}

    id        = db.Column(db.BigInteger, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("app.users.id"), nullable=True)
    session_id= db.Column(db.Integer, db.ForeignKey("app.sessions.id"), nullable=True)

    # e.g., 'login', 'logout', 'game_start', 'game_end', 'attempt', 'help', ...
    event_type = db.Column(db.String(50), nullable=False)

    # put arbitrary structured payload here (what happened)
    data = db.Column(JSONB, nullable=False, server_default=db.text("'{}'::jsonb"))

    created_at = db.Column(db.DateTime(timezone=True),
                           nullable=False,
                           server_default=func.now())

    user    = db.relationship("User", backref=db.backref("events", lazy="dynamic"))
    session = db.relationship("Session", backref=db.backref("events", lazy="dynamic"))

    def __repr__(self):
        return f"<Event id={self.id} type={self.event_type!r}>"

