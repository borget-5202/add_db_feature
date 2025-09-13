from flask import request
from ..db import db
from ..models import Game, Puzzle  # adjust import paths if needed

def log_event(session_id:int, game_id:int, event_type:str, puzzle_id:int|None=None, props:dict|None=None, user_id:int|None=None):
    db.session.execute(
        db.text("""
            INSERT INTO app.events (session_id, game_id, event_type, puzzle_id, user_id, props)
            VALUES (:sid, :gid, :etype, :pid, :uid, :props::jsonb)
        """),
        {"sid": session_id, "gid": game_id, "etype": event_type, "pid": puzzle_id, "uid": user_id, "props": (props or {})}
    )
    db.session.commit()

