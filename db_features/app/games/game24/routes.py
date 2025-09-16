# app/games/game24/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response, current_app
from flask_login import login_required, current_user
from typing import List, Dict, Any, Optional, Tuple
import random

from ...db import db
from ...models import User, Game, GameSession    # GameSession alias points to Session
from uuid import uuid4
import json, time, logging
import re

from .track import get_or_create_puzzle, log_attempt
from .logic.puzzle_store import init_store, get_puzzle_by_id, get_puzzle_by_values, random_pick_by_level, PUZZLES_BY_KEY

from .logic import game24_utils as gutils
SESSIONS = gutils.SESSIONS
default_state = gutils.default_state
_pool = gutils._pool
_pool_report = gutils._pool_report
_pool_score = gutils._pool_score
bump_played_once = gutils.bump_played_once
bump_solved = gutils.bump_solved
bump_revealed = gutils.bump_revealed
bump_skipped = gutils.bump_skipped
bump_help = gutils.bump_help
bump_attempt = gutils.bump_attempt
bump_deal_swap = gutils.bump_deal_swap
get_or_create_session_id = gutils.get_or_create_session_id
get_guest_id = gutils.get_guest_id
_values_key = gutils._values_key


logger = logging.getLogger(__name__)

bp = Blueprint(
    "game24",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static"  # gives /game24/static/...
)

def _ensure_guest_user():
    u = User.query.filter_by(username="guest").first()
    if not u:
        # use a unique-ish local email to avoid collisions
        u = User(
            username="guest",
            email="guest@littleteachers.local",
            password_hash="!",  # placeholder; not used for login
            role="student",
            is_active=True,
        )
        db.session.add(u)
        db.session.commit()
    return u


# ----------------------------
# basic page + session seed
# ----------------------------
# in play(), change key/name -> slug/title:

from flask import current_app

@bp.get("/api/debug/puzzle")
@login_required
def api_debug_puzzle():
    # dev-only for safety
    if not current_app.debug:
        return ("Not found", 404)
    case_id = request.args.get("case_id")
    values  = request.args.get("values")  # comma-separated, e.g. "1,5,7,13"

    p = None
    if case_id:
        try:
            p = get_puzzle_by_id(int(case_id))
        except Exception:
            pass
    elif values:
        try:
            vals = [int(x) for x in values.split(",")]
            p = get_puzzle_by_values(vals)
        except Exception:
            pass

    return jsonify({
        "ok": bool(p),
        "has_solutions": bool(p and p.get("solutions")),
        "puzzle": p
    }), 200


@bp.get("/")
def index():
    return redirect(url_for("game24.play"))  # canonical route


@bp.get("/play")
@login_required
def play():
    game = Game.query.filter_by(slug="game24").first()
    if not game:
        game = Game(slug="game24", title="24-Point (Classic)", modality="cards")
        db.session.add(game)
        db.session.flush()

    sess = GameSession(session_uuid=uuid4(), user_id=current_user.id, game_id=game.game_id)
    db.session.add(sess)
    db.session.commit()
    api_base = url_for("game24.api_next").rsplit("/", 1)[0]  # "/game24/api"

    resp = make_response(render_template("play.html", 
                                         session_id=sess.id,
                                         game24_api_base=api_base))
    resp.set_cookie("db_session_id", str(sess.id), max_age=3600, httponly=True, samesite="Lax", path="/")
    if not request.cookies.get("session_id"):
        resp.set_cookie("session_id", str(sess.session_uuid), max_age=1800, samesite="Lax", path="/")
    return resp


# ----------------------------
# in-memory state (ported)
# ----------------------------
#SESSIONS = {}  # { sid: state }

def _stats_payload(state):
    st = state.get('stats', {})
    return {
        "played": int(st.get("played", 0)),
        "solved": int(st.get("solved", 0)),
        "revealed": int(st.get("revealed", 0)),
        "skipped": int(st.get("skipped", 0)),
        "difficulty": st.get("by_level", {}),
        "help_single": int(st.get("help_single", 0)),
        "help_all": int(st.get("help_all", 0)),
        "answer_attempts": int(st.get("answer_attempts", 0)),
        "answer_correct": int(st.get("answer_correct", 0)),
        "answer_wrong": int(st.get("answer_wrong", 0)),
        "deal_swaps": int(st.get("deal_swaps", 0)),
    }

# ----------------------------
# load answers.json (once)
# ----------------------------

# (legacy compatibility: PUZZLES_BY_KEY now comes from store)

# ----------------------------
# pools & level selection (ported)
# ----------------------------


def _counting_level_for_current(state, puzzle, requested_level):
    p = _pool(state)
    if p.get('mode') in ('custom','competition') or state.get('current_case_id'):
        return puzzle.get('level') or normalize_level(requested_level)
    rl = normalize_level(requested_level)
    return 'challenge' if rl in ('challenge','nosol') else rl

def _competition_time_left(state):
    end = state.get('competition_ends_at')
    if not end: return None
    left = int(round(end - time.time()))
    return max(0, left)

# ----------------------------
# images (fixed to blueprint static)
# ----------------------------
SUITS = ['D','S','H','C']
def _rank_code(n): return {1:'A',10:'T',11:'J',12:'Q',13:'K'}.get(int(n), str(n))

def _cards_to_images(cards, theme="classic"):
    out = []
    for i, n in enumerate(cards):
        rank = _rank_code(n)
        suit = SUITS[i % len(SUITS)]
        code = f"{rank}{suit}"
        # NOTE: this matches app/games/game24/static/game24/assets/images/classic/*.png
        url = url_for("game24.static", filename=f"assets/images/classic/{code}.png")
        out.append({"code": code, "url": url})
    return out


_RANK_MAP = {"A": "1", "T": "10", "J": "11", "Q": "12", "K": "13"}


def _normalize_expr_for_eval(expr: str) -> str:
    """
    Convert rank tokens and common math glyphs into plain arithmetic:
      A,T,J,Q,K → 1,10,11,12,13   (only when used as standalone tokens)
      ×,x       → *
      ÷         → /
      –,—,−     → -
    Also removes whitespace.
    """
    if not isinstance(expr, str):
        return expr
    s = expr.strip()

    # unify common glyphs first
    s = (s.replace("×", "*").replace("x", "*").replace("X", "*")
           .replace("÷", "/")
           .replace("–", "-").replace("—", "-").replace("−", "-"))

    # replace rank letters as whole tokens using word boundaries
    def repl(m):
        ch = m.group(1).upper()
        return _RANK_MAP.get(ch, ch)

    s = re.sub(r"\b([ATJQKatjqk])\b", repl, s)

    # remove whitespace
    s = re.sub(r"\s+", "", s)
    return s

# ----------------------------
# API routes (ported)
# ----------------------------
@bp.get("/api/pool_report")
def pool_report():
    sid = get_or_create_session_id(request)
    state = SESSIONS.setdefault(sid, default_state())
    st = state.get("stats", {})
    payload = {
        "played": int(st.get("played", 0)),
        "solved": int(st.get("solved", 0)),
        "revealed": int(st.get("revealed", 0)),
        "skipped": int(st.get("skipped", 0)),
        "difficulty": st.get("by_level", {}),
        "help_single": int(st.get("help_single", 0)),
        "help_all": int(st.get("help_all", 0)),
        "answer_attempts": int(st.get("answer_attempts", 0)),
        "answer_correct": int(st.get("answer_correct", 0)),
        "answer_wrong": int(st.get("answer_wrong", 0)),
        "deal_swaps": int(st.get("deal_swaps", 0)),
    }
    return jsonify({"ok": True, "stats": payload})

@bp.get("/api/next")
def api_next():
    sid = get_or_create_session_id(request)
    state = SESSIONS.setdefault(sid, default_state())

    theme = request.args.get("theme", "classic")
    #level = request.args.get("level", "easy")
    #case_id = request.args.get("case_id", type=int)
    seq = int(request.args.get("seq", 0))

    #state   = _get_state()
    pstate  = _pool(state)
    case_id = request.args.get("case_id")
    level   = (request.args.get("level") or "").strip().lower()
    mode    = (pstate.get("mode") or "").strip().lower()
    ids     = pstate.get("ids") or []

    # if the user dealt away previous hand without interaction, count deal swap
    prev_cid = state.get("current_case_id")
    if prev_cid and not state.get("hand_interacted"):
        bump_deal_swap(state)

    left = _competition_time_left(state)
    if left is not None and left <= 0:
        return jsonify({"competition_over": True}), 403

    pstate = _pool(state)
    puzzle = None

    if case_id:
        puzzle = get_puzzle_by_id(int(case_id))
        if not puzzle:
            return jsonify({"error": f"Case #{case_id} not found"}), 404
        logger.info("api_next (case_id=%s): -> case_id=%s values=%s",
                    case_id or "unknow_mode", case_id, puzzle.get("cards"))
    elif pstate["mode"] in ("custom","competition"):
        if pstate["done"] or pstate["index"] >= len(pstate["ids"]):
            pstate["done"] = True
            return jsonify({"error": "Pool complete", "pool_done": True}), 400
        case_id = pstate["ids"][pstate["index"]]
        pstate["index"] += 1
        puzzle = get_puzzle_by_id(int(case_id))
        logger.info("api_next (mode=%s): -> case_id=%s values=%s",
                    mode or "unknow_mode", case_id, puzzle.get("cards"))
    else:
        puzzle =  random_pick_by_level(level, state)
        logger.info("api_next (level=%s): -> case_id=%s values=%s",
                    level or "default", case_id, puzzle.get("cards"))

    # finalize state
    values = list(map(int, puzzle.get("cards") or []))
    state["current_case_id"] = int(puzzle.get("case_id"))
    state["hand_interacted"] = False
    state["current_effective_level"] = _counting_level_for_current(state, puzzle, level)
    state["current_started_at"] = time.time()

    # payload
    images = _cards_to_images(values, theme)
    resp_payload = {
        "ok": True,
        "seq": seq + 1,
        "case_id": int(puzzle.get("case_id")),
        "question": values,                 # array is fine; your UI prints it
        "values": values,
        "images": images,
        "help_disabled": bool(state.get("help_disabled")),
        "pool_done": bool(pstate["done"] or (pstate["mode"] in ("custom","competition") and pstate["index"] >= len(pstate["ids"]))),
    }
    if left is not None and left > 0:
        resp_payload["time_left"] = left

    # set cookie for session id
    resp = make_response(jsonify(resp_payload))
    cookie_base = (sid.split(':', 1)[0]) if ':' in sid else sid
    if not request.cookies.get("session_id"):
        resp.set_cookie("session_id", cookie_base, max_age=1800, samesite="Lax", path="/")
    logger.info("api_next seq=%s -> case_id=%s values=%s", seq, resp_payload["case_id"], values)
    return resp

def _find_puzzle_row_by_caseid(cid: int):
    ext4 = f"{cid:04d}"
    return (Puzzle.query
            .filter(Puzzle.external_id.in_([ext4, str(cid)]))
            .order_by(Puzzle.id.desc())
            .first())

@bp.post("/api/check")
def api_check():
    sid = get_or_create_session_id(request)
    state = SESSIONS.setdefault(sid, default_state())

    data = request.get_json(force=True) or {}

    case_id = data.get("case_id")
    expr = data.get("expr")
    # legacy names (old client)
    values = data.get("values")
    answer = data.get("answer")
    if expr is None and answer is not None:
        expr = str(answer)

    # Resolve case_id from values if missing (legacy support)
    if not case_id and values:
        try:
            vals = list(map(int, values))
        except Exception:
            vals = []
        key = "-".join(map(str, sorted(vals)))
        p = get_puzzle_by_values(vals)
        if p:
            case_id = int(p.get("case_id"))

    if not case_id or expr is None:
        return jsonify({"ok": False, "reason": "Missing case_id or expr"}), 200

    # ---- helpers to keep api_check short ----
    def _elapsed_ms_for(case_id_int):
        try:
            sid = request.cookies.get("session_id") or "anon"
            st = SESSIONS.get(sid) or {}
            if st.get("current_case_id") == int(case_id_int):
                started = st.get("current_started_at")
                if started:
                    return int((time.time() - float(started)) * 1000)
        except Exception:
            pass
        return None
    
    
    def _finish(resp: dict, *, case_id=None, expr=None, values=None, status: str | None = None):
        logger.info("   ~~~ in _finish, resp = %s",str(resp) )
        logger.info("   ~~~ in _finish, case_id = %s",str(case_id) )
        try:
            db_sess_id = request.cookies.get("db_session_id")
            if db_sess_id is not None and case_id is not None:
                cid = int(case_id)
                s = status if status is not None else ("solved" if resp.get("ok") else "failed")
                log_attempt(
                            session_id=int(db_sess_id),
                            puzzle_id=case_id,
                            status=s,
                            elapsed_ms=_elapsed_ms_for(cid),
                            score=100 if s == "solved" else 0,
                            detail={"expr": expr, "values": values, "kind": resp.get("kind")},
                )
        except Exception as e:
            logger.exception("api_check: logging failed: %s", e)
        return jsonify(resp), 200


    puzzle = get_puzzle_by_id(int(case_id))
    if not puzzle:
        return jsonify({"ok": False, "reason": f"Puzzle {case_id} not found"}), 200

    # ----- OLD-WAY "NO SOLUTION" FAST-PATH (ported) -----
    ns = (expr or "").strip().lower()
    if ns in {"no solution", "nosolution", "no sol", "nosol", "0", "-1"}:
        # ensure stats reflect an attempt / interaction once
        level_for_stats = state.get("current_effective_level") or puzzle.get("level") or "unknown"
        try:
            # old route tracked "played once"
            bump_played_once(state, level_for_stats)  # noqa
        except Exception:
            # minimal fallback if helper not present
            st = state.setdefault("stats", {})
            st["played"] = int(st.get("played", 0)) + 1

        state["hand_interacted"] = True

        sols_exist = bool(puzzle.get("solutions"))
        if not sols_exist:
            # correct: truly no solution
            bump_attempt(state, True)
            try:
                _mark_case_status(state, case_id, "good")    # noqa
                _set_case_solved(state, case_id)             # noqa
            except Exception:
                pass
            bump_solved(state, level_for_stats)
            resp ={
                "ok": True,
                "value": None,
                "kind": "no-solution",
                "stats": _stats_payload(state),
            }
            return _finish(resp, case_id=case_id, expr=expr, status="failed")
        else:
            # incorrect: there IS a solution
            bump_attempt(state, False)
            try:
                _mark_case_status(state, case_id, "attempt")  # noqa
            except Exception:
                pass
            in_comp = (_pool(state).get("mode") == "competition")
            resp = {
                "ok": False,
                "reason": "Incorrect — this case is solvable." + (
                    " (Help is disabled in competition.)" if in_comp else " Try Help to see one."
                ),
                "kind": "solvable" if in_comp else "help-available",
                "stats": _stats_payload(state),
            }
            logger.info("calling _finish, case_id=%s, expr=%s", str(case_id), str(expr) )
            return _finish(resp, case_id=case_id, expr=expr, status="failed")

    # normalize A/T/J/Q/K and glyphs so users can type 'J+T+J+T', etc.
    expr_norm = _normalize_expr_for_eval(expr)

    # evaluator that enforces “use all 4 input numbers once”
    from .logic.evaluator import safe_eval

    try:
        # IMPORTANT: pass the four numbers to enforce “use each once”
        nums = values if values else (puzzle.get("cards") or [])
        value = safe_eval(expr_norm, nums)
        ok = (abs(value - 24) < 1e-6)
    except ValueError as e:
        bump_attempt(state, False)
        logger.info("api_check fail(case_id=%s): %s (expr=%r -> %r)", case_id, e, expr, expr_norm)
        resp = {
            "ok": False,
            "reason": str(e),          # shown by UI
            "expr": expr,
            "expr_norm": expr_norm,
            "stats": _stats_payload(state),
        }
        return _finish(resp, case_id=case_id, expr=expr, status="failed")
    except Exception as e:
        bump_attempt(state, False)
        logger.warning("api_check unexpected error: %s", e)
        resp = {
            "ok": False,
            "reason": "Unsupported expression.",
            "expr": expr,
            "expr_norm": expr_norm,
            "stats": _stats_payload(state),
        }
        return _finish(resp, case_id=case_id, expr=expr, status="failed")

    # reach here → evaluated successfully
    level_for_stats = state.get("current_effective_level") or puzzle.get("level") or "unknown"
    try:
        bump_played_once(state, level_for_stats)  # old behavior
    except Exception:
        st = state.setdefault("stats", {})
        st["played"] = int(st.get("played", 0)) + 1

    state["hand_interacted"] = True

    if ok:
        try:
            _mark_case_status(state, case_id, "good")   # noqa
            _set_case_solved(state, case_id)            # noqa
        except Exception:
            pass
        bump_attempt(state, True)
        bump_solved(state, level_for_stats)
        resp = {
            "ok": True,
            "case_id": int(case_id),
            "expr": expr,
            "expr_norm": expr_norm,
            "value": value,
            "stats": _stats_payload(state),
        }
        return _finish(resp, case_id=case_id, expr=expr, status="solved")
    else:
        try:
            _mark_case_status(state, case_id, "attempt")  # noqa
        except Exception:
            pass
        bump_attempt(state, False)
        resp = {
            "ok": False,
            "case_id": int(case_id),
            "expr": expr,
            "expr_norm": expr_norm,
            "value": value,      # UI shows “(got …)”
            "reason": "",        # causes UI to fall back to “Try again!”
            "stats": _stats_payload(state),
        }
        return _finish(resp, case_id=case_id, expr=expr, status="failed")

def _coerce_int_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        try:    return [int(x) for x in val]
        except: return []
    if isinstance(val, str):
        parts = [p.strip() for p in val.replace("[","").replace("]","").split(",")]
        try:    return [int(x) for x in parts if x]
        except: return []
    return []

def _get_case_and_values_from_request():
    # Accept both GET query and POST body, and alias keys.
    if request.method == "GET":
        data = request.args
    else:
        data = (request.get_json(silent=True) or {})
    # common aliases
    case_id = data.get("case_id") or data.get("caseId") or data.get("id")
    values  = data.get("values")  or data.get("cards")  or data.get("ranks")
    if values is not None:
        values = _coerce_int_list(values)
    return case_id, values, (data.get("all") in (True, "1", "true", "yes"))


@bp.route("/api/help", methods=["GET","POST"])
def api_help():
    try:
        state = _get_state()  # type: ignore[name-defined]
        _ = _pool(state)      # type: ignore[name-defined]
    except Exception:
        state = {}

    case_id, values, want_all = _get_case_and_values_from_request()
    if not case_id and not values:
        return jsonify({"ok": False, "reason": "Missing case_id or values"}), 200

    # Resolve by case_id or by values
    if case_id:
        try:
            puzzle = get_puzzle_by_id(int(case_id))
        except Exception:
            puzzle = None
    else:
        puzzle = get_puzzle_by_values(values or [])
        if puzzle:
            case_id = int(puzzle.get("case_id"))

    if not puzzle:
        return jsonify({"ok": False, "reason": "Puzzle not found"}), 200

    sols = puzzle.get("solutions") or []
    has_solution = bool(sols)

    # build payload; fall back if helpers are missing
    if want_all:
        try:
            bump_help(state, all=True)  # type: ignore[name-defined]
        except Exception:
            pass
        payload = sols
    else:
        try:
            bump_help(state, all=False)  # type: ignore[name-defined]
        except Exception:
            pass
        one = None
        try:
            one = pick_one_solution(sols)  # type: ignore[name-defined]
        except Exception:
            one = random.choice(sols) if sols else None
        payload = [one] if one else []

    # try to include stats; otherwise send empty dict
    try:
        stats_payload = _stats_payload(state)  # type: ignore[name-defined]
    except Exception:
        stats_payload = {}

    resp = {
        "ok": True,
        "has_solution": has_solution,
        "solutions": payload,
        "solution": payload,   # legacy key some UIs expect
        "stats": stats_payload,
    }

    # ---- DB logging ----
    try:
        db_sess_id = request.cookies.get("db_session_id")
        if db_sess_id and case_id is not None:
            log_attempt(session_id=int(db_sess_id), puzzle_id=case_id, status="revealed")
    except Exception as e:
        logger.exception("api_help: logging failed: %s", e)

    return jsonify(resp), 200

@bp.post("/api/restart")
def api_restart():
    """
    Reset the current tab's in-memory game state (stats, pool, timers, etc.).
    Does NOT drop any DB rows; it's purely the in-memory session for this tab.
    """
    sid = get_or_create_session_id(request)
    # Replace state with a fresh copy
    SESSIONS[sid] = default_state()
    logger.info("api_restart: reset session %s", sid)

    return jsonify({
        "ok": True,
        "message": "Session reset",
        "stats": _stats_payload(SESSIONS[sid]),
    }), 200

def _coerce_id_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        try:    return [int(x) for x in val]
        except: return []
    if isinstance(val, str):
        parts = [p.strip() for p in val.replace("[","").replace("]","").split(",")]
        try:    return [int(x) for x in parts if x]
        except: return []
    return []

@bp.post("/api/pool")
def api_pool():
    """
    Configure a pool of puzzles for this tab's session.

    Request JSON:
      {
        "mode": "custom" | "competition" | "off",
        "ids": [1,2,3, ...],                 # optional; required for custom/competition
        "duration_seconds": 600              # optional; competition only; default 600 (10m)
      }

    Behavior:
      - mode=="custom": deals puzzles from ids in order; help enabled
      - mode=="competition": deals puzzles from ids in order; help disabled; timer starts
      - mode=="off" (or empty ids): return to free-play (random by level), help enabled
    """
    sid = get_or_create_session_id(request)
    state = SESSIONS.setdefault(sid, default_state())

    data = request.get_json(force=True) or {}
    mode = (data.get("mode") or "").strip().lower()

    # be permissive about the field name
    ids = data.get("ids")
    if ids is None:
        ids = data.get("case_ids")

    if mode in ("off", "", None):
        # Clear pool → free play
        state["help_disabled"] = False
        p = _pool(state)
        p.update({"mode": None, "ids": [], "index": 0, "done": False, "status": {}})
        state["competition_ends_at"] = None
        logger.info("api_pool: cleared pool (free play) for sid=%s", sid)
        return jsonify({
            "ok": True,
            "mode": None,
            "count": 0,
            "time_left": None,
            "help_disabled": False,
            "stats": _stats_payload(state),
        }), 200

    if mode not in ("custom", "competition"):
        return jsonify({"ok": False, "reason": "mode must be 'custom', 'competition', or 'off'"}), 200

    # Validate IDs -> only keep known case_ids
    try:
        case_ids = [int(x) for x in (ids or [])]
    except Exception:
        case_ids = []

    #valid_ids = [cid for cid in case_ids if cid in PUZZLES_BY_ID]
    valid_ids   = [cid for cid in case_ids if get_puzzle_by_id(cid) is not None]
    if not valid_ids:
        return jsonify({"ok": False, "reason": "No valid case IDs provided"}), 200

    # Set pool
    p = _pool(state)
    p.update({
        "mode": mode,
        "ids": valid_ids,
        "index": 0,
        "done": False,
        "status": {},   # you can store per-case correctness here if you like
    })

    # Help & competition timer
    if mode == "competition":
        duration = int(data.get("duration_seconds") or 600)  # default 10 minutes
        state["help_disabled"] = True
        state["competition_ends_at"] = time.time() + duration
    else:
        state["help_disabled"] = False
        state["competition_ends_at"] = None

    tl = _competition_time_left(state)
    logger.info("api_pool: mode=%s count=%d duration=%s",
                mode, len(valid_ids), (tl if tl is not None else "-"))

    return jsonify({
        "ok": True,
        "mode": mode,
        "count": len(valid_ids),
        "time_left": tl,                      # seconds (None when not competition)
        "help_disabled": state["help_disabled"],
        "stats": _stats_payload(state),
    }), 200


@bp.post("/api/exit")
def api_exit():
    """
    Old-style exit: return a full stats payload and "unlock" free play (clear pool).
    New: if hard=true, also clear cookie/state and include next_url (home) so the UI can redirect.
    """
    sid = get_or_create_session_id(request)
    state = SESSIONS.setdefault(sid, default_state())
    gid = get_guest_id(request) or state.get("guest_id")

    # Build stats payload similar to the old one
    st = state.get("stats", {})
    score_map, unfinished = _pool_score(state)
    p = _pool(state)

    payload = {
        "played": int(st.get("played", 0)),
        "solved": int(st.get("solved", 0)),
        "revealed": int(st.get("revealed", 0)),
        "skipped": int(st.get("skipped", 0)),
        "difficulty": st.get("by_level", {}),

        # action counters
        "help_single": int(st.get("help_single", 0)),
        "help_all": int(st.get("help_all", 0)),
        "answer_attempts": int(st.get("answer_attempts", 0)),
        "answer_correct": int(st.get("answer_correct", 0)),
        "answer_wrong": int(st.get("answer_wrong", 0)),
        "deal_swaps": int(st.get("deal_swaps", 0)),

        "guest_id": gid,
        "pool_mode": p.get("mode"),
        "pool_len": len(p.get("ids") or []),
        "pool_score": score_map,
        "unfinished": unfinished,
        "pool_report": _pool_report(state),
    }

    # Clear pool → free play (matches old behavior)
    p["mode"] = None
    p["done"] = False
    p["index"] = 0
    p["ids"] = []
    state["help_disabled"] = False
    state["competition_ends_at"] = None

    hard = str(request.args.get("hard", "false")).lower() in ("1", "true", "yes", "y")
    resp_body = {"ok": True, "stats": payload}

    # If "hard exit": also forget the in-memory session + clear cookie and provide home URL
    if hard:
        try:
            if sid in SESSIONS:
                del SESSIONS[sid]
        except Exception:
            pass
        # Compute a home URL; adjust if your home route differs
        try:
            # If you have a home blueprint endpoint, use that; else fallback to "/"
            from flask import url_for
            next_url = url_for("home.index")
        except Exception:
            next_url = "/"

        resp_body["next_url"] = next_url

        resp = make_response(jsonify(resp_body))
        resp.set_cookie("session_id", "", max_age=0)
        return resp

    # Soft/old-style exit: keep cookie/session, just return the payload
    return jsonify(resp_body), 200

