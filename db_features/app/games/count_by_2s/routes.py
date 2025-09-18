# app/games/count_by_2s/routes.py
from __future__ import annotations
import random, time
from datetime import datetime, timezone
from typing import Dict, Any, Set
from flask import Blueprint, request, jsonify, render_template, make_response, url_for, current_app
from flask_login import login_required, current_user
from app.db import db
from app.models import Game, Session as GameSession  # your existing models
from .logic.puzzle_store import init_store, pool_report as store_pool_report, random_next, expected_final

bp = Blueprint("count_by_2s", __name__, url_prefix="/count_by_2s",
               template_folder="templates", static_folder="static")

# --------- Session state (in-memory, per cookie) ----------
SESSIONS: Dict[str, Dict[str, Any]] = {}

#4) Make the preload cap adjustable
#Default cap: 100 (via DEFAULT_CAP).
#Override with:
#Env: export CB2S_CAP=200
#Flask config: app.config["CB2S_CAP"] = 200 (then warmup uses it)

def default_state() -> Dict[str, Any]:
    return {
        "stats": {
            "played": 0,
            "solved": 0,
            "revealed": 0,
            "skipped": 0,
            "total_time": 0,  # seconds
            "answer_attempts": 0,
            "answer_correct": 0,
            "answer_wrong": 0,
        },
        "seen": { "easy": set(), "medium": set(), "hard": set(), "all": set() },  # type: ignore
        "current_case_id": None,
        "current_started_at": None,
        "counted_this_puzzle": False,  # ensure 'played' increments once per puzzle
    }

def _get_session_key() -> str | None:
    return request.cookies.get("db_session_id")

def _get_state() -> Dict[str, Any]:
    key = _get_session_key() or "anon"
    if key not in SESSIONS:
        SESSIONS[key] = default_state()
    return SESSIONS[key]

def _get_db_session() -> GameSession | None:
    sid = request.cookies.get("db_session_id")
    if not sid:
        return None
    try:
        return GameSession.query.get(int(sid))
    except Exception:
        return None

def _stats_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    s = state["stats"]
    return {
        "played": s["played"],
        "solved": s["solved"],
        "revealed": s["revealed"],
        "skipped": s["skipped"],
        "total_time": s["total_time"],
        "answer_attempts": s["answer_attempts"],
        "answer_correct": s["answer_correct"],
        "answer_wrong": s["answer_wrong"],
    }

def _now_utc():
    return datetime.now(timezone.utc)

def _add_elapsed_to_total(state: Dict[str, Any]):
    started = state.get("current_started_at")
    if started:
        dt = (datetime.now(timezone.utc) - started).total_seconds()
        state["stats"]["total_time"] += int(dt)
    state["current_started_at"] = None

def _ensure_played_once(state: Dict[str, Any]):
    if not state.get("counted_this_puzzle"):
        state["stats"]["played"] += 1
        state["counted_this_puzzle"] = True

# --------- Cards / images ----------
SUITS = ("S", "H", "D", "C")

def _code(n: int) -> str:
    if n == 1:  return "A"
    if n == 11: return "J"
    if n == 12: return "Q"
    if n == 13: return "K"
    return str(n)

def _images_for(cards: list[int]) -> list[dict]:
    # randomize suit each render to keep things fun
    suit_choices = random.choices(SUITS, k=4)
    codes = [f"{_code(cards[i])}{suit_choices[i]}" for i in range(4)]
    # IMPORTANT: adjust blueprint name below if yours differs
    mk = lambda code: {
        "code": code,
        "url": url_for("games_assets_bp.static", filename=f"cards/{code}.png")
    }
    return [mk(c) for c in codes]

def _row_to_payload(puz, seq: int, level: str, state: Dict[str, Any], pool_done: bool = False) -> Dict[str, Any]:
    return {
        "ok": True,
        "seq": seq,
        "case_id": puz.id,
        "difficulty": level,
        "question": [ _code(v) for v in puz.cards ],
        "values": puz.cards,
        "images": _images_for(puz.cards),
        "pool_done": pool_done,
        "stats": _stats_payload(state),
    }

# --------- Warmup (optional) ----------
def warmup(app=None):
    cap = None
    try:
        cap = (app and app.config.get("CB2S_CAP")) or None
    except Exception:
        cap = None
    init_store(force=False, cap=cap)

# --------- Routes ----------
@bp.get("/play")
@login_required
def play():
    # ensure store ready
    warmup(current_app)

    game = Game.query.filter_by(slug="count-by-2s").first()
    level = (request.args.get("level") or "easy").lower()

    # create a DB session row if needed
    sess = _get_db_session()
    if not sess:
        sess = GameSession(
            session_uuid=uuid.uuid4(),
            user_id=current_user.id if hasattr(current_user, "id") else None,
            game_id=game.game_id if game else None,
            started_at=_now_utc(),
            completed=False,
            meta={},
        )
        db.session.add(sess)
        db.session.commit()

    # make sure in-memory state exists
    state = _get_state()
    # reset per-puzzle flags for first screen
    state["counted_this_puzzle"] = False
    state["current_started_at"] = _now_utc()

    # pick first puzzle (seq=0 for the client; the UI will show Q1)
    puz, pool_done = random_next(level, avoid_ids=state["seen"].get(level, set()))
    if puz:
        state["current_case_id"] = puz.id
    payload = _row_to_payload(puz, seq=0, level=level, state=state, pool_done=pool_done)

    resp = make_response(render_template(
        "cb2s_play.html",
        title=(game.title if game else "Count by 2s"),
        game24_api_base="/count_by_2s/api",   # reusing the same JS var name
        first_payload=payload,
    ))
    # keep cookie
    if not request.cookies.get("db_session_id"):
        resp.set_cookie("db_session_id", str(sess.id), httponly=True, samesite="Lax")
    return resp

@bp.get("/api/pool_report")
def api_pool_report():
    warmup(current_app)
    return jsonify({"ok": True, "pools": store_pool_report(), "stats": _stats_payload(_get_state())})

@bp.get("/api/next")
def api_next():
    warmup(current_app)
    level = (request.args.get("level") or "easy").lower()
    seq = int(request.args.get("seq") or 0)

    state = _get_state()
    seen: Set[int] = state["seen"].setdefault(level, set())

    puz, pool_done = random_next(level, avoid_ids=seen)
    if puz:
        seen.add(puz.id)
        state["current_case_id"] = puz.id
        state["counted_this_puzzle"] = False
        state["current_started_at"] = _now_utc()

    payload = _row_to_payload(puz, seq=seq, level=level, state=state, pool_done=pool_done)
    return jsonify(payload), 200

@bp.post("/api/check")
def api_check():
    j = request.get_json(silent=True) or {}
    values = j.get("values") or []
    answer = j.get("answer")
    try:
        ans = int(str(answer).strip())
    except Exception:
        ans = None

    state = _get_state()
    ok = False
    if isinstance(values, list) and len(values) == 4 and ans is not None:
        target = expected_final(values)
        ok = (ans == target)

    # first interaction on this puzzle counts as played
    _ensure_played_once(state)
    state["stats"]["answer_attempts"] += 1
    if ok:
        state["stats"]["answer_correct"] += 1
        state["stats"]["solved"] += 1
        _add_elapsed_to_total(state)
    else:
        state["stats"]["answer_wrong"] += 1

    return jsonify({"ok": ok, "stats": _stats_payload(state)}), 200

@bp.post("/api/help")
def api_help():
    j = request.get_json(silent=True) or {}
    values = j.get("values") or []
    state = _get_state()

    # first interaction counts as played
    _ensure_played_once(state)
    state["stats"]["revealed"] += 1
    _add_elapsed_to_total(state)

    solutions = []
    has_solution = False
    if isinstance(values, list) and len(values) == 4:
        final = expected_final(values)
        # simple, kid-friendly trail:
        a, b, c, d = values
        solutions = [f"{_code(a)} + {b} = {a+b}",
                     f"{a+b} + {c} = {a+b+c}",
                     f"{a+b+c} + {d} = {final}",
                     f"Final: {final}"]
        has_solution = True

    return jsonify({"ok": True, "has_solution": has_solution, "solutions": solutions, "stats": _stats_payload(state)}), 200

@bp.post("/api/restart")
def api_restart():
    key = _get_session_key()
    if key and key in SESSIONS:
        del SESSIONS[key]
    # give the client zeros
    return jsonify({"ok": True, "stats": _stats_payload(default_state())}), 200

@bp.post("/api/exit")
def api_exit():
    # If the client posts stats, we trust them less than our server state.
    j = request.get_json(silent=True) or {}
    posted = j.get("stats") or {}
    state = _get_state()
    # add current elapsed if mid-puzzle
    _add_elapsed_to_total(state)
    final_stats = _stats_payload(state)

    # persist to DB session meta
    sess = _get_db_session()
    if sess:
        sess.ended_at = _now_utc()
        if sess.meta is None:
            sess.meta = {}
        sess.meta["stats"] = final_stats
        db.session.add(sess)
        db.session.commit()

    # clear in-memory
    key = _get_session_key()
    if key and key in SESSIONS:
        del SESSIONS[key]

    return jsonify({
        "ok": True,
        "next_url": url_for("home.index"),
        "stats": final_stats
    }), 200

