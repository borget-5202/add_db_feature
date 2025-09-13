from datetime import datetime
from flask import request
from uuid import UUID
from ...db import db
from ...models import Attempt, Puzzle, Game

def get_or_create_puzzle(game_slug: str, external_id: str, title=None, difficulty=None, payload=None):
    game = Game.query.filter_by(slug=game_slug).first()
    if not game:
        # should already exist via seed; create if missing
        game = Game(slug=game_slug, title="24-Point (Classic)", modality="cards")
        db.session.add(game)
        db.session.flush()

    p = Puzzle.query.filter_by(game_id=game.id, external_id=external_id).first()
    if not p:
        p = Puzzle(
            game_id=game.id,
            external_id=external_id,
            title=title,
            difficulty=difficulty,
            content_json=payload or {},
            is_active=True,
        )
        db.session.add(p)
        db.session.flush()
    return p

def log_attempt(session_id: int, puzzle_id: int, status: str, elapsed_ms: int | None = None,
                score: int = 0, detail: dict | None = None):
    a = Attempt(
        session_id=session_id,
        puzzle_id=puzzle_id,
        status=status,                  # 'started' | 'skipped' | 'solved' | 'failed' | 'revealed'
        started_at=datetime.utcnow(),   # if you have separate start, pass it in instead
        ended_at=datetime.utcnow(),
        elapsed_ms=elapsed_ms,
        score=score,
        detail_json=detail or {}
    )
    db.session.add(a)
    db.session.commit()
    return a.id

