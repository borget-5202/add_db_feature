# app/games/sum_4_cards/sum4_routes.py
import time
import json
import secrets
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from flask import (
    request, render_template, jsonify, current_app, make_response
)
from sqlalchemy import text
from app import db
from . import bp

# Try to use your shared core helpers; fall back to local logic if missing
_persist = None
_get_sid = None
try:
    # Your repo named this path "app/game/core/game_core.py"
    from app.game.core.game_core import persist_session_from_id as _persist
    from app.game.core.game_core import get_or_create_session_id as _get_sid
except Exception:
    # Optional alt path if you later move core under games/
    try:
        from app.games.core.game_core import persist_session_from_id as _persist
        from app.games.core.game_core import get_or_create_session_id as _get_sid
    except Exception:
        _persist = None
        _get_sid = None

GAME_KEY = "sum_4_cards"

# ---- small helpers ---------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)

def _fetch_game_row() -> Dict[str, Any]:
    row = db.session.execute(
        text("SELECT id, title, metadata FROM app.games WHERE game_key=:k"),
        {"k": GAME_KEY},
    ).mappings().first()
    if not row:
        raise RuntimeError(f"Game {GAME_KEY} not found. Insert into app.games first.")
    return dict(row)

def _fetch_case(case_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Return {case_id, cards_key, ranks, sum_pips}. If case_id is None, pick random.
    """
    if case_id is None:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k
        ORDER BY random()
        LIMIT 1
        """
        row = db.session.execute(text(sql), {"k": GAME_KEY}).mappings().first()
    else:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k AND v.case_id = :cid
        """
        row = db.session.execute(text(sql), {"k": GAME_KEY, "cid": case_id}).mappings().first()

    if not row:
        raise RuntimeError(f"No puzzle found for {GAME_KEY} (case_id={case_id}).")
    return dict(row)

def _envelope(game: Dict[str, Any], case: Dict[str, Any], session_sid: str) -> Dict[str, Any]:
    ranks: List[int] = case["ranks"]
    reveal_groups = [[0], [1], [2], [3]]  # dealer feel: one-by-one
    return {
        "session_sid": session_sid,       # client can keep this, no need to post it back
        "game_key": GAME_KEY,
        "title": game["title"],
        "case_id": case["case_id"],
        "reveal_mode": "server",
        "table": {
            "slots": 4,
            "layout": [0, 1, 2, 3],
            "cards": [
                {"id": "c0", "rank": int(ranks[0]), "visible": False, "face": "front"},
                {"id": "c1", "rank": int(ranks[1]), "visible": False, "face": "front"},
                {"id": "c2", "rank": int(ranks[2]), "visible": False, "face": "front"},
                {"id": "c3", "rank": int(ranks[3]), "visible": False, "face": "front"},
            ],
            "deck": []
        },
        "reveal": {"groups": reveal_groups, "server_step": 0},
        "grading": {"type": "sum", "target": int(case["sum_pips"])},
        "ui_hints": {"pace": "normal", "audio_cues": False, "show_back_card": False},
        # embed minimal state so client can be stateless across steps if needed
        "_state": {"start_ms": _now_ms()}
    }

# ---- routes ----------------------------------------------------------------

@bp.get("/play")
def play():
    game = _fetch_game_row()
    # NOTE: template name is sum4_play.html 
    return render_template("sum_4_cards/sum4_play.html", game=game, game_key=GAME_KEY)

@bp.post("/api/start")
def api_start():
    data = request.get_json(silent=True) or {}
    case_id = data.get("case_id")
    game = _fetch_game_row()
    case = _fetch_case(case_id)

    # session sid cookie (try core helper, else a simple cookie)
    session_sid = None
    try:
        if _get_sid:
            # assumes your helper returns a (sid, response?) — if not, ignore
            session_sid = _get_sid(request)
        else:
            session_sid = request.cookies.get("session_sid") or secrets.token_hex(16)
    except Exception:
        session_sid = request.cookies.get("session_sid") or secrets.token_hex(16)

    env = _envelope(game, case, session_sid)

    # send cookie if it didn't exist (no redirect; client keeps JSON and cookie)
    resp = make_response(jsonify({"ok": True, "envelope": env}))
    if not request.cookies.get("session_sid"):
        resp.set_cookie("session_sid", session_sid, max_age=60*60*24*365, samesite="Lax")
    return resp

@bp.post("/api/step")
def api_step():
    """
    Server-controlled reveal: advance one group each call.
    Client posts: {"server_step": <int>, "answers": [<optional>]}
    """
    payload = request.get_json(silent=True) or {}
    server_step = int(payload.get("server_step", 0))

    # The client holds the envelope; we only need to echo back "reveal" and next step.
    # Reveal groups are always 4 steps: [[0],[1],[2],[3]]
    groups = [[0], [1], [2], [3]]
    if server_step < 0 or server_step >= len(groups):
        return jsonify({"ok": True, "reveal": [], "server_step": server_step, "done": True})

    reveal_now = groups[server_step]
    next_step = server_step + 1
    done = next_step >= len(groups)
    return jsonify({"ok": True, "reveal": reveal_now, "server_step": next_step, "done": done})

@bp.post("/api/finish")
def api_finish():
    """
    Client posts final answer: {"case_id": <int>, "answer": <number>, "envelope": {...}}
    We grade and persist to app.game_sessions.
    """
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case_id")
    answer = payload.get("answer")

    if answer is None:
        return jsonify({"ok": False, "error": "Missing 'answer'"}), 400

    # We trust the envelope for ranks/target, but re-lookup is cheap and safer
    case = _fetch_case(case_id)
    target = int(case["sum_pips"])
    is_correct = int(answer) == target

    # build summary_json
    summary = {
        "game_key": GAME_KEY,
        "case_id": int(case["case_id"]),
        "cards_key": case["cards_key"],
        "ranks": [int(x) for x in case["ranks"]],
        "expected_sum": target,
        "user_answer": int(answer),
        "correct": bool(is_correct),
        "reveal_mode": "server",
    }

    # gameplay counters
    played = 1
    solved = 1 if is_correct else 0
    incorrect = 0 if is_correct else 1
    skipped = 0
    help_all = 0

    # find game_id
    g = _fetch_game_row()
    game_id = int(g["id"])

    # started/ended (approx from client; you can also accept elapsed_ms)
    start_ms = int((payload.get("envelope") or {}).get("_state", {}).get("start_ms", _now_ms()))
    end_ms = _now_ms()

    # session_sid (cookie), client id if you use it in your core
    session_sid = request.cookies.get("session_sid")

    # persist using your shared helper if available; else fallback
    persisted_id = None
    try:
        if _persist:
            # known signature from your project
            state = {
                "session_sid": session_sid,
                "client_id": None,
                "guest_id": None,
                "started_at_ms": start_ms,
                "ended_at_ms": end_ms,
                "played": played,
                "solved": solved,
                "skipped": skipped,
                "incorrect": incorrect,
                "help_all": help_all,
            }
            persisted_id = _persist(
                db=db,
                game_id=game_id,
                game_key=GAME_KEY,   # your helper accepts slug/ key label
                state=state,
                summary=summary,
            )
        else:
            # Fallback direct insert that fits your app.game_sessions shape
            public_code = secrets.token_hex(4)
            row = db.session.execute(
                text("""
                    INSERT INTO app.game_sessions
                    (game_id, session_sid, client_id, guest_id,
                     public_code, player_name,
                     started_at_ms, ended_at_ms,
                     played, solved, skipped, incorrect, help_all,
                     summary_json, created_at, share_code)
                    VALUES
                    (:game_id, :session_sid, NULL, NULL,
                     :public_code, NULL,
                     :started_ms, :ended_ms,
                     :played, :solved, :skipped, :incorrect, :help_all,
                     :summary::jsonb, now(), NULL)
                    RETURNING id
                """),
                dict(
                    game_id=game_id,
                    session_sid=session_sid,
                    public_code=public_code,
                    started_ms=start_ms,
                    ended_ms=end_ms,
                    played=played,
                    solved=solved,
                    skipped=skipped,
                    incorrect=incorrect,
                    help_all=help_all,
                    summary=json.dumps(summary),
                ),
            ).first()
            db.session.commit()
            persisted_id = int(row[0])
    except Exception as e:
        current_app.logger.exception("persist failed: %s", e)
        return jsonify({"ok": False, "error": "persist_failed"}), 500

    return jsonify({"ok": True, "correct": is_correct, "expected": target, "id": persisted_id})

