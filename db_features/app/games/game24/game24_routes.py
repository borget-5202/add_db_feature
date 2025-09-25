# app/games/game24/game24_routes.py
# Target-aware version (24 / 10 / 36). Keeps existing features (summary, CSV, exit).
from __future__ import annotations

import ast
import csv
import io
import json
import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.routing import BuildError

from app.db import db
from app.models import Game, GameSession

# ---- shared core helpers (import these from your game_core.py) ----
from app.games.core.game_core import (
    # store / session
    SESSIONS,
    default_state,
    get_or_create_session_id,
    get_guest_id,
    stats_payload,
    # values / expr / assets
    card_images,
    normalize_rank_expr,
    values_key,
    # timers / pools
    _mark_case_status,
    _pool,
    _pool_report,
    _pool_score,
    competition_time_left,
    _set_case_solved,
    # stats
    bump_attempt,
    bump_deal_swap,
    bump_help,
    bump_played_once,
    bump_revealed,
    bump_skipped,
    bump_solved,
    ensure_played_once,
    # exit/persist helpers
    finalize_open_hand,
    persist_session_from_id,
    persist_session_random,  # unused here; keep available
    reset_runtime_state,
    # NEW: exact solvers you added
    solve_one,
    enumerate_solutions,
)

# ---- Game24 puzzle store (book solutions for target=24) ----
from app.games.core.puzzle_store_game24 import Game24Store
from app.games.core.puzzle_store_game24 import get_store, warmup_store

logger = logging.getLogger(__name__)
bp = Blueprint(
    "game24",
    __name__,
    url_prefix="/games/game24",
    static_folder="static",
    template_folder="templates",
)

# -----------------------------------------------------------------------------
# Small per-request helpers
# -----------------------------------------------------------------------------
def _sid() -> str:
    return get_or_create_session_id(request)

def _state() -> Dict[str, Any]:
    sid = _sid()
    return SESSIONS.setdefault(sid, default_state())

def now_ms() -> int:
    return int(time.time() * 1000)

def _get_target(state: Dict[str, Any], data: Optional[dict] = None) -> int:
    """Resolve target from JSON body or query args or state; default 24."""
    if data and "target" in data:
        try:
            t = int(data["target"])
            if t < -100: t = -100
            if t < -100: t = -100
            state["target"] = t
            return t
        except Exception:
            pass
    if "target" in request.args:
        try:
            t = int(request.args.get("target"))
            if t < -100: t = -100
            if t < -100: t = -100
            state["target"] = t
            return t
        except Exception:
            pass
    return int(state.get("target", 24))

def _begin_hand(state: Dict[str, Any], case_id: int, level: Optional[str]) -> None:
    """
    Finalize any existing hand (unsolved_exit if no outcome), then start a new one.
    """
    cur = state.get("current_hand")
    if cur and not cur.get("final_outcome"):
        cur["final_outcome"] = "unsolved_exit"
        cur["ended_at_ms"] = now_ms()
        state.setdefault("per_puzzle", []).append(cur)

    state["current_hand"] = {
        "case_id": case_id,
        "level": level,
        "target": int(state.get("target", 24)),
        "attempts": 0,
        "incorrect_attempts": 0,
        "helped": False,
        "skipped": False,
        "solved": False,
        "started_at_ms": now_ms(),
        "ended_at_ms": None,
        "final_outcome": None,
    }
    state["counted_this_puzzle"] = False
    state["hand_interacted"] = False

def _current_hand(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return state.get("current_hand")

def _finalize_hand(state: Dict[str, Any], outcome: Optional[str] = None) -> None:
    cur = state.get("current_hand")
    if not cur:
        return
    if outcome and not cur.get("final_outcome"):
        cur["final_outcome"] = outcome
    if not cur.get("ended_at_ms"):
        cur["ended_at_ms"] = now_ms()
    per = state.setdefault("per_puzzle", [])
    if (not per) or (per and per[-1] is not cur):
        per.append(cur)
    state["current_hand"] = None

def _clear_pool(state):
    p = _pool(state)
    p.update({"mode": None, "ids": [], "index": 0, "status": {}, "score": {}, "done": False})
    state["help_disabled"] = False
    state["competition_ends_at"] = None


# -----------------------------------------------------------------------------
# Safe arithmetic evaluation for /api/check
# -----------------------------------------------------------------------------
_ALLOWED_NODES = {
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Load,
    ast.Constant,
    ast.Tuple,
    ast.List,
}

def _safe_eval_number(expr: str) -> float:
    node = ast.parse(expr, mode="eval")

    def _rec(n):
        if type(n) not in _ALLOWED_NODES:
            raise ValueError(f"disallowed: {type(n).__name__}")
        if isinstance(n, ast.Expression):
            return _rec(n.body)
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float)):
                return float(n.value)
            raise ValueError("constant must be number")
        if isinstance(n, ast.UnaryOp):
            v = _rec(n.operand)
            if isinstance(n.op, ast.UAdd):
                return v
            if isinstance(n.op, ast.USub):
                return -v
            raise ValueError("bad unary op")
        if isinstance(n, ast.BinOp):
            a = _rec(n.left)
            b = _rec(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                if abs(b) < 1e-12:
                    raise ZeroDivisionError("division by zero")
                return a / b
            if isinstance(n.op, ast.Pow):
                if abs(a) > 1e6 or abs(b) > 12:
                    raise ValueError("pow too large")
                return a ** b
            raise ValueError("bad binop")
        raise ValueError("bad node")

    return _rec(node)

def _normalize_expr(expr: str) -> str:
    s = (expr or "")
    s = s.replace("^", "**").replace("×", "*").replace("∗", "*").replace("·", "*")
    s = s.replace("÷", "/").replace("／", "/")
    s = s.replace("−", "-").replace("—", "-").replace("–", "-")
    s = normalize_rank_expr(s)
    return s

def _expr_uses_exact_values(expr: str, values: List[int]) -> bool:
    try:
        node = ast.parse(expr, mode="eval")
    except Exception:
        return False
    lits: List[int] = []

    class LitVisitor(ast.NodeVisitor):
        def visit_Constant(self, n: ast.Constant):
            if isinstance(n.value, (int, float)):
                v = int(n.value)
                lits.append(v)

    LitVisitor().visit(node)
    try:
        return sorted(lits) == sorted([int(x) for x in values])
    except Exception:
        return False

# -----------------------------------------------------------------------------
# Book/stored solutions (24 only) & "no solution" checks
# -----------------------------------------------------------------------------
def _solutions_for_24(values: List[int]) -> Tuple[List[str], bool]:
    store = get_store()
    try:
        sols = store.solve(values)
    except AttributeError:
        try:
            sols = store.get_solutions(values)
        except AttributeError:
            sols = []
    sols = sols or []
    return sols, (len(sols) > 0)

def _no_solution_correct(values: List[int], case_id: Optional[int], target: int) -> Tuple[bool, str]:
    """
    Return (is_correct, method), respecting the selected target.
    - For target=24: use your book/store (fast and authoritative).
    - For other targets: try to find ONE solution via solver. If none → correct.
    """
    if int(target) == 24:
        # Prefer case_id lookup when possible for speed/accuracy
        store = get_store()
        if case_id:
            try:
                cid = int(case_id)
                puz = store.get_by_id(cid)
                if puz:
                    has = bool(puz.get("solutions", []))
                    return (not has, "case_id")
            except Exception:
                pass
        sols, has = _solutions_for_24(values)
        return (not has, "values")
    else:
        expr = solve_one(values, int(target))
        return (expr is None, "solver")

def _pick_random_for_target(store, level, state, target: int, max_tries: int = 60):
    """
    Randomly pick a puzzle; if target != 24 and solvable-only is on,
    loop until we find a solvable one (or give up after max_tries).
    """
    # recent_keys logic stays the same
    recent = state.get("recent_keys") or []
    tried = 0
    chosen = None
    while tried < max_tries:
        puz, _pool_done = store.random_pick(level, recent)
        chosen = puz
        if not puz:
            break
        # keep recent list tidy
        try:
            from app.games.core.game_core import values_key
            k = values_key(puz["cards"])
            rk = state.setdefault("recent_keys", [])
            if k not in rk:
                rk.append(k)
                if len(rk) > 50:
                    state["recent_keys"] = rk[-50:]
        except Exception:
            pass

        if int(target) == 24:
            return puz  # any is fine
        # non-24 → require solvable
        try:
            from app.games.core.game_core import solve_one
            if solve_one(puz["cards"], int(target)):
                return puz
        except Exception:
            # if solver fails, fall back to showing anyway
            return puz
        tried += 1
    return chosen  # last seen, even if unsolvable (we tried!)


# -----------------------------------------------------------------------------
# Debug wrappers for stats (optional)
# -----------------------------------------------------------------------------
def debug_bump_attempt(state: Dict[str, Any], correct: bool):
    logger.info(
        "BUMP_ATTEMPT: correct=%s, before: attempts=%s, correct=%s, wrong=%s",
        correct,
        state.get("stats", {}).get("answer_attempts", 0),
        state.get("stats", {}).get("answer_correct", 0),
        state.get("stats", {}).get("answer_wrong", 0),
    )
    bump_attempt(state, correct)
    logger.info(
        "BUMP_ATTEMPT: after: attempts=%s, correct=%s, wrong=%s",
        state.get("stats", {}).get("answer_attempts", 0),
        state.get("stats", {}).get("answer_correct", 0),
        state.get("stats", {}).get("answer_wrong", 0),
    )

def debug_bump_skipped(state: Dict[str, Any]):
    logger.info("BUMP_SKIPPED: before: skipped=%s", state.get("stats", {}).get("skipped", 0))
    bump_skipped(state)
    logger.info("BUMP_SKIPPED: after: skipped=%s", state.get("stats", {}).get("skipped", 0))

def debug_bump_solved(state: Dict[str, Any], level: Optional[str] = None):
    logger.info("BUMP_SOLVED: before: solved=%s", state.get("stats", {}).get("solved", 0))
    bump_solved(state, level)
    logger.info("BUMP_SOLVED: after: solved=%s", state.get("stats", {}).get("solved", 0))

def debug_bump_revealed(state: Dict[str, Any]):
    logger.info("BUMP_REVEALED: before: revealed=%s", state.get("stats", {}).get("revealed", 0))
    bump_revealed(state)
    logger.info("BUMP_REVEALED: after: revealed=%s", state.get("stats", {}).get("revealed", 0))

def debug_bump_deal_swap(state: Dict[str, Any]):
    if "bump_deal_swap" in globals():
        logger.info("BUMP_DEAL_SWAP: before: deal_swaps=%s", state.get("stats", {}).get("deal_swaps", 0))
        bump_deal_swap(state)
        logger.info("BUMP_DEAL_SWAP: after: deal_swaps=%s", state.get("stats", {}).get("deal_swaps", 0))
    else:
        logger.info("BUMP_DEAL_SWAP: function not available")

def _debug_sid(where: str) -> None:
    try:
        sid_cookie = request.cookies.get("session_id")
        sid_runtime = _sid()
        st = _state()
        logger.info(
            "[%s] sid_runtime=%s sid_cookie=%s per_puzzle=%d current_hand=%s stats=%s",
            where,
            sid_runtime,
            sid_cookie,
            len(st.get("per_puzzle", [])),
            bool(st.get("current_hand")),
            st.get("stats"),
        )
    except Exception as e:
        logger.warning("[%s] sid debug failed: %s", where, e)

# -----------------------------------------------------------------------------
# Page routes
# -----------------------------------------------------------------------------
@bp.get("/")
def index():
    return redirect(url_for("game24.play"))

@bp.get("/play")
@login_required
def play():
    """
    Render the play page with proper session setup.
    """
    # Ensure game exists
    game = Game.query.filter_by(slug="game24").first()
    if not game:
        game = Game(slug="game24", title="24-Point Card Game", modality="cards", subject="math")
        db.session.add(game)
        db.session.commit()

    # Create session record
    sess = GameSession(
        session_uuid=str(uuid.uuid4()),
        user_id=current_user.id,
        game_id=game.game_id,
        started_at=None,
        ended_at=None,
        completed=False,
        meta={},
    )
    db.session.add(sess)
    db.session.commit()

    # API base visible to JS
    qs_target = request.args.get("target")
    try:
        init_target = int(qs_target) if qs_target not in (None, "custom") else None
    except Exception:
        init_target = None
    api_base = url_for("game24.api_next").rsplit("/", 1)[0]
    nonce = getattr(g, "csp_nonce", "")

    resp = make_response(
        render_template("play.html", init_target=init_target, csp_nonce=nonce, api_base=api_base, session_id=str(sess.id))
    )
    resp.set_cookie("db_session_id", str(sess.id), httponly=True, samesite="Lax")
    if not request.cookies.get("session_id"):
        resp.set_cookie("session_id", str(sess.session_uuid), samesite="Lax")
    return resp

# -----------------------------------------------------------------------------
# API: Next (deal) with Go, pool, and timer support
# -----------------------------------------------------------------------------
@bp.get("/api/next")
def api_next():
    sid = _sid()
    logger.info("API_NEXT Session ID: %s", sid)
    store = get_store()
    if not store.by_id:
        logger.warning("Store not loaded, forcing load...")
        store.load(force=True)
        logger.info("Store loaded with %d puzzles", len(store.by_id))

    logger.info("=== api_next CALLED ===")
    logger.info("Request args: %s", dict(request.args))
    logger.info("Client IP: %s", request.remote_addr)

    state = _state()
    _debug_sid("api_next")

    # Read and store the selected target (default 24)
    target = _get_target(state)  # from args/state
    theme = (request.args.get("theme") or "classic").strip().lower()
    level = (request.args.get("level") or "easy").strip().lower()
    seq = int(request.args.get("seq") or 0)
    case_id_param = request.args.get("case_id")

    # Finalize unfinished hand before dealing a new one
    cur = _current_hand(state)
    if cur and not cur.get("final_outcome"):
        cur["ended_at_ms"] = now_ms()
        if (cur.get("attempts", 0) == 0) and not cur.get("helped"):
            cur["skipped"] = True
            outcome = "skipped"
            bump_skipped(state)
        else:
            if cur.get("incorrect_attempts", 0) > 0:
                outcome = "skipped_after_wrong"
            elif cur.get("helped"):
                outcome = "skipped_after_help"
            else:
                outcome = "unsolved_exit"
        _finalize_hand(state, outcome)

    logger.info(
        "Pool state - mode: %s, ids: %s, index: %d, done: %s",
        state.get("pool", {}).get("mode"),
        state.get("pool", {}).get("ids"),
        state.get("pool", {}).get("index", 0),
        state.get("pool", {}).get("done", False),
    )

    tleft = competition_time_left(state)
    if tleft is not None and tleft <= 0:
        logger.info("Competition over - time left: %s", tleft)
        return jsonify({"competition_over": True, "time_left": 0}), 403

    def build_payload(puz: Optional[Dict[str, Any]], pool_done: bool = False) -> Dict[str, Any]:
        vals = puz["cards"] if puz else []
        payload = {
            "ok": True,
            "seq": seq,
            "case_id": int(puz["case_id"]) if puz else None,
            "question": vals,
            "values": vals,
            "images": card_images(vals) if vals else [],
            "help_disabled": bool(state.get("help_disabled")),
            "pool_done": bool(pool_done),
            "target": int(state.get("target", 24)),
            "stats": stats_payload(state),
        }
        tl = competition_time_left(state)
        if tl is not None:
            payload["time_left"] = tl

        logger.info(
            "Built payload - case_id: %s, values: %s, pool_done: %s, target: %s",
            payload["case_id"],
            payload["values"],
            payload["pool_done"],
            payload["target"],
        )
        logger.debug("api_next send to frontend: raw stats_payload: %r", stats_payload(state))
        return payload

    # -- Explicit case_id mode
    if case_id_param:
        logger.info("Case ID mode requested: %s", case_id_param)
        try:
            cid = int(case_id_param)
            puz = store.get_by_id(cid)
            if not puz:
                return jsonify({"ok": False, "error": f"case_id {cid} not found"}), 404
            _begin_hand(state, int(puz["case_id"]), level)
            state["current_case_id"] = int(puz["case_id"])
            return jsonify(build_payload(puz, pool_done=False)), 200
        except Exception as e:
            logger.error("Error in case_id mode: %s", e)
            return jsonify({"ok": False, "error": "invalid case_id"}), 400

    # -- Pool modes
    p = _pool(state)
    if p.get("mode") in ("custom", "competition") and p.get("ids"):
        logger.info("Pool mode active: %s with %d IDs", p["mode"], len(p["ids"]))
    
        # Competition timer hard-stop
        tleft = competition_time_left(state)
        if p["mode"] == "competition" and tleft is not None and tleft <= 0:
            return jsonify({"competition_over": True, "time_left": 0}), 403
    
        ids = p["ids"]
        idx = int(p.get("index") or 0)
    
        # Already finished?
        if p.get("done") or idx >= len(ids):
            if p["mode"] == "custom":
                logger.info("Custom pool completed. Auto-exiting pool and falling back to random.")
                _clear_pool(state)
                # fall through to normal random pick below
            else:
                # Competition: keep pool_done behavior
                return jsonify(build_payload(None, pool_done=True)), 200
        else:
            # Serve next ID from pool
            cid = int(ids[idx])
            puz = store.get_by_id(cid)
    
            # Advance index and set done flag
            p["index"] = idx + 1
            p["done"] = (p["index"] >= len(ids))
    
            if not puz:
                logger.warning("Pool contained missing case_id=%s; skipping.", cid)
                if p["done"]:
                    if p["mode"] == "custom":
                        logger.info("Custom pool finished after skipping; auto-exiting.")
                        _clear_pool(state)
                        # fall through to normal random pick
                    else:
                        return jsonify(build_payload(None, pool_done=True)), 200
                else:
                    # Try the next pool entry immediately
                    return api_next()
            else:
                _begin_hand(state, int(puz["case_id"]), level)
                state["current_case_id"] = int(puz["case_id"])
                _mark_case_status(state, int(puz["case_id"]), "shown")
                return jsonify(build_payload(puz, pool_done=p["done"])), 200

    # -- Normal random pick
    logger.info("Normal random pick for level: %s", level)
    puz = None
    pool_done = False
    try:
        puz = _pick_random_for_target(store, level, state, target)
        pool_done = False
        if puz:
            logger.info("random_pick result: %s", puz["case_id"])
        else:
            logger.warning("random_pick returned None")
        #puz, pool_done = store.random_pick(level, state.get("recent_keys") or [])
        #logger.info("random_pick result: %s, pool_done: %s", puz["case_id"] if puz else "None", pool_done)
    except TypeError as e:
        logger.error("random_pick TypeError: %s - using fallback", e)
        puz, pool_done = None, False

        #try:
        #    puz = store.random_pick(level)
        #    logger.info("Fallback random_pick: %s", puz["case_id"] if puz else "None")
        #except Exception as fallback_error:
        #    logger.error("Fallback also failed: %s", fallback_error)
        #    puz = None

    if puz:
        try:
            k = values_key(puz["cards"])
            rk = state.setdefault("recent_keys", [])
            if k not in rk:
                rk.append(k)
                if len(rk) > 50:
                    state["recent_keys"] = rk[-50:]
            logger.info("Added to recent_keys: %s (now %d keys)", k, len(rk))
        except Exception as e:
            logger.error("Error tracking recent keys: %s", e)

        _begin_hand(state, int(puz["case_id"]), level)
        state["current_case_id"] = int(puz["case_id"])
        logger.info("Selected puzzle: case_id %s - values: %s", puz["case_id"], puz["cards"])
    else:
        logger.warning("No puzzle selected for level: %s", level)

    response = build_payload(puz, pool_done=pool_done)
    logger.info("=== api_next COMPLETE ===")
    return jsonify(response), 200

# -----------------------------------------------------------------------------
# API: Check
# -----------------------------------------------------------------------------
@bp.post("/api/check")
def api_check():
    logger.info("=== api_check CALLED ===")
    state = _state()
    _debug_sid("api_check")
    data = request.get_json(force=True) or {}

    values = data.get("values") or data.get("vals")
    answer = (data.get("answer") or "").strip()
    case_id = data.get("case_id")
    target = _get_target(state, data)

    logger.info("Check case_id=%s, target=%s, values=%s, answer=%s", case_id, target, values, answer)

    if not values or not isinstance(values, list):
        return jsonify({"ok": False, "reason": "Missing or invalid values"}), 400

    ensure_played_once(state)
    logger.debug("api_check received: stats_payload: %r", stats_payload(state))

    # "No solution" fast-path
    if answer.lower() in {"no solution", "nosolution", "no-solution", "n", "0", "-1"}:
        correct, method_used = _no_solution_correct(values, case_id, target)
        logger.info("No-solution claim: correct=%s via %s", correct, method_used)
        bump_attempt(state, correct=correct)
        if correct:
            bump_solved(state, state.get("current_effective_level"))
            cur = _current_hand(state)
            if cur:
                cur["solved"] = True
                cur["final_outcome"] = "solved_no_help"
                cur["ended_at_ms"] = now_ms()
                _finalize_hand(state, outcome=cur["final_outcome"])
            _set_case_solved(state, state.get("current_case_id") or -1)
            return jsonify({"ok": True, "kind": "no-solution", "stats": stats_payload(state)}), 200
        else:
            cur = _current_hand(state)
            if cur:
                cur["attempts"] += 1
                cur["incorrect_attempts"] += 1
            return jsonify(
                {"ok": False, "reason": f"This hand has a solution for target {target}.", "stats": stats_payload(state)}
            ), 200

    # Normal expression path
    norm = _normalize_expr(answer)
    if not _expr_uses_exact_values(norm, values):
        bump_attempt(state, correct=False)
        cur = _current_hand(state)
        if cur:
            cur["attempts"] += 1
            cur["incorrect_attempts"] += 1
        return jsonify({"ok": False, "reason": "Expression must use each card exactly once."}), 200

    try:
        val = _safe_eval_number(norm)
    except Exception:
        bump_attempt(state, correct=False)
        cur = _current_hand(state)
        if cur:
            cur["attempts"] += 1
            cur["incorrect_attempts"] += 1
        return jsonify({"ok": False, "reason": "Unsafe or invalid expression"}), 200

    # compare to chosen target
    correct = abs(val - float(target)) < 1e-6
    bump_attempt(state, correct=correct)
    cur = _current_hand(state)

    if not correct:
        if cur:
            cur["attempts"] += 1
            cur["incorrect_attempts"] += 1
        return jsonify({"ok": False, "reason": f"Your result = {val:g}, target = {target}"}), 200

    # success
    bump_solved(state, state.get("current_effective_level"))
    if cur:
        cur["attempts"] += 1
        cur["solved"] = True
        cur["final_outcome"] = "solved_with_help" if cur.get("helped") else "solved_no_help"
        cur["ended_at_ms"] = now_ms()
        _finalize_hand(state, outcome=cur["final_outcome"])
    _set_case_solved(state, state.get("current_case_id") or -1)
    return jsonify({"ok": True, "kind": "exact", "stats": stats_payload(state), "target": target}), 200

# -----------------------------------------------------------------------------
# API: Help  (use store for 24; solver for other targets)
# -----------------------------------------------------------------------------
@bp.post("/api/help")
def api_help():
    logger.info("=== api_help CALLED ===")
    state = _state()
    _debug_sid("api_help")
    if state.get("help_disabled"):
        return jsonify(
            {"ok": False, "error": "help_disabled", "reason": "Help is disabled in competition mode."}
        ), 403

    data = request.get_json(force=True) or {}
    values = data.get("values")
    all_solutions = bool(data.get("all"))
    case_id = data.get("case_id")
    target = _get_target(state, data)

    if not values:
        return jsonify({"ok": False, "reason": "Missing values"}), 400

    ensure_played_once(state)
    bump_help(state, all=all_solutions)
    bump_revealed(state)

    cur = _current_hand(state)
    if cur:
        cur["helped"] = True

    # Target-aware solution source
    if int(target) == 24:
        store = get_store()
        puz = None
        if case_id:
            try:
                puz = store.get_by_id(int(case_id))
            except Exception:
                puz = None
        if not puz:
            # fallback by values
            sols24, has24 = _solutions_for_24(values)
            if not has24:
                return jsonify(
                    {"ok": True, "has_solution": False, "solutions": [], "stats": stats_payload(state)}
                ), 200
            out = sols24 if all_solutions else sols24[:1]
            return jsonify(
                {"ok": True, "has_solution": True, "solutions": out, "stats": stats_payload(state), "target": target}
            ), 200
        else:
            sols = puz.get("solutions", []) or []
            if not sols:
                return jsonify(
                    {"ok": True, "has_solution": False, "solutions": [], "stats": stats_payload(state)}
                ), 200
            out = sols if all_solutions else sols[:1]
            return jsonify(
                {"ok": True, "has_solution": True, "solutions": out, "stats": stats_payload(state), "target": target}
            ), 200

    # Non-24 target: compute on demand
    if all_solutions:
        sols = enumerate_solutions(values, int(target), limit=50)
        if not sols:
            return jsonify(
                {
                    "ok": True,
                    "has_solution": False,
                    "solutions": [],
                    "message": f"No solution for target {target} with these cards.",
                    "stats": stats_payload(state),
                    "target": target,
                }
            ), 200
        return jsonify(
            {"ok": True, "has_solution": True, "solutions": sols, "count": len(sols), "stats": stats_payload(state), "target": target}
        ), 200
    else:
        expr = solve_one(values, int(target))
        if not expr:
            return jsonify(
                {
                    "ok": True,
                    "has_solution": False,
                    "solutions": [],
                    "message": f"No solution for target {target} with these cards.",
                    "stats": stats_payload(state),
                    "target": target,
                }
            ), 200
        return jsonify(
            {"ok": True, "has_solution": True, "solutions": [expr], "stats": stats_payload(state), "target": target}
        ), 200

# -----------------------------------------------------------------------------
# API: Skip
# -----------------------------------------------------------------------------
@bp.post("/api/skip")
def api_skip():
    logger.info("=== api_skip CALLED ===")
    sid = _sid()
    logger.info("API_SKIP Session ID: %s", sid)
    state = _state()
    _debug_sid("api_skip")

    bump_played_once(state)
    bump_skipped(state)
    bump_deal_swap(state)

    cur = _current_hand(state)
    if cur and not cur.get("final_outcome"):
        cur["skipped"] = True
        cur["final_outcome"] = "skipped"
        cur["ended_at_ms"] = now_ms()
        state.setdefault("per_puzzle", []).append(cur)
        state["current_hand"] = None

    logger.debug("api_skip send to frontend: raw stats_payload: %r", stats_payload(state))
    return jsonify({"ok": True, "stats": stats_payload(state)}), 200

# -----------------------------------------------------------------------------
# API: Restart
# -----------------------------------------------------------------------------
@bp.post("/api/restart")
def api_restart():
    sid = _sid()
    SESSIONS[sid] = default_state()
    return jsonify({"ok": True, "stats": stats_payload(SESSIONS[sid])}), 200

# -----------------------------------------------------------------------------
# Summary building (shared by /api/summary and /api/exit)
# -----------------------------------------------------------------------------
def _build_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("=== _build_summary CALLED ===")
    logger.info("Raw state stats: %s", state.get("stats", {}))
    logger.info("per_puzzle count: %d", len(state.get("per_puzzle", [])))
    logger.info("current_hand exists: %s", bool(state.get("current_hand")))

    per = state.get("per_puzzle", [])[:]
    cur = state.get("current_hand")
    if cur and not cur.get("final_outcome"):
        tmp = dict(cur)
        tmp["final_outcome"] = "unsolved_exit"
        tmp["ended_at_ms"] = tmp.get("ended_at_ms") or now_ms()
        per.append(tmp)

    totals = {"solved": 0, "helped": 0, "incorrect": 0, "skipped": 0}
    buckets = {
        "solved_ids": [],
        "solved_no_help_ids": [],
        "solved_with_help_ids": [],
        "helped_ids": [],
        "incorrect_ids": [],
        "skipped_ids": [],
        "revealed_no_attempt_ids": [],
        "revealed_after_attempts_ids": [],
        "unsolved_exit_ids": [],
        "first_try_correct_ids": [],
        "struggle_before_solve_ids": [],
    }
    by_level: Dict[str, Dict[str, int]] = {}

    for row in per:
        cid = int(row["case_id"])
        lvl = row.get("level") or "unknown"
        by = by_level.setdefault(lvl, {"played": 0, "solved": 0})
        by["played"] += 1

        if row.get("solved"):
            totals["solved"] += 1
            by["solved"] += 1
            buckets["solved_ids"].append(cid)
            if row.get("helped"):
                buckets["solved_with_help_ids"].append(cid)
            else:
                buckets["solved_no_help_ids"].append(cid)
        else:
            if row.get("helped"):
                totals["helped"] += 1
                buckets["helped_ids"].append(cid)
                if int(row.get("attempts") or 0) == 0:
                    buckets["revealed_no_attempt_ids"].append(cid)
                else:
                    buckets["revealed_after_attempts_ids"].append(cid)
            if row.get("skipped"):
                totals["skipped"] += 1
                buckets["skipped_ids"].append(cid)
            if (row.get("incorrect_attempts") or 0) > 0:
                totals["incorrect"] += 1
                buckets["incorrect_ids"].append(cid)
            if not row.get("solved") and not row.get("skipped"):
                buckets["unsolved_exit_ids"].append(cid)

    by_case: Dict[int, List[Dict[str, Any]]] = {}
    for r in per:
        by_case.setdefault(int(r["case_id"]), []).append(r)

    for cid, rows in by_case.items():
        rows.sort(key=lambda r: int(r.get("started_at_ms") or 0))
        first = rows[0]
        solved_ever = any(bool(x.get("solved")) for x in rows)
        if first.get("solved") and int(first.get("attempts") or 0) <= 1 and not first.get("helped"):
            buckets["first_try_correct_ids"].append(cid)
        elif solved_ever:
            buckets["struggle_before_solve_ids"].append(cid)

    def fmt_ids(label: str, ids: List[int]) -> str:
        if not ids:
            return f"  {label} [0]: —\n"
        uniq = sorted(set(ids))
        return f"  {label} [{len(uniq)}]: " + ", ".join(str(i) for i in uniq) + "\n"

    lines = []
    lines.append("Totals")
    lines.append(f"  solved:   {totals['solved']}")
    lines.append(f"  helped:   {totals['helped']}")
    lines.append(f"  incorrect:{totals['incorrect']}")
    lines.append(f"  skipped:  {totals['skipped']}")
    lines.append("")
    lines.append("Case IDs")
    lines.append(fmt_ids("Solved (no help)", buckets["solved_no_help_ids"]).rstrip())
    lines.append(fmt_ids("Solved (with help)", buckets["solved_with_help_ids"]).rstrip())
    lines.append(fmt_ids("Helped (any)", buckets["helped_ids"]).rstrip())
    lines.append(fmt_ids("Incorrect (had wrong attempts)", buckets["incorrect_ids"]).rstrip())
    lines.append(fmt_ids("Skipped", buckets["skipped_ids"]).rstrip())
    lines.append(fmt_ids("Revealed no attempt", buckets["revealed_no_attempt_ids"]).rstrip())
    lines.append(fmt_ids("Revealed after attempts", buckets["revealed_after_attempts_ids"]).rstrip())
    lines.append(fmt_ids("Unsolved exit", buckets["unsolved_exit_ids"]).rstrip())
    lines.append(fmt_ids("First-try correct", buckets["first_try_correct_ids"]).rstrip())
    lines.append(fmt_ids("Struggled but solved", buckets["struggle_before_solve_ids"]).rstrip())
    lines.append("")
    if by_level:
        lines.append("By Level")
        for lvl, row in by_level.items():
            acc = (row["solved"] * 100.0 / row["played"]) if row["played"] else 0.0
            lines.append(f"  {lvl:<10} played={row['played']:<4} solved={row['solved']:<4} acc={acc:.0f}%")

    report_html = "<pre>" + "\n".join(lines) + "</pre>"
    return {
        "totals": totals,
        "buckets": buckets,
        "by_level": by_level,
        "per_puzzle": per,
        "report_html": report_html,
    }

# -----------------------------------------------------------------------------
# API: Summary (peek)
# -----------------------------------------------------------------------------
@bp.post("/api/summary")
def api_summary():
    logger.info("=== api_summary CALLED ===")
    state = _state()
    _debug_sid("api_summary")
    snap = _build_summary(state)
    export_url = url_for("game24.api_export_csv")
    return jsonify({"ok": True, "stats": stats_payload(state), "play_summary": snap, "export_url": export_url}), 200

# -----------------------------------------------------------------------------
# API: Exit (finalize session; return summary and optional links)
# -----------------------------------------------------------------------------
def _home_url():
    for ep in ("home.index", "games.index", "index", "game24.index"):
        try:
            return url_for(ep)
        except BuildError:
            continue
    return "/"

@bp.post("/api/exit")
def api_exit():
    state = _state()
    # finalize any in-flight hand
    finalize_open_hand(state, finalize_cb=_finalize_hand)
    # build summary
    snap = _build_summary(state)
    # persist
    GAME24_ID, GAME24_SLUG = 1, "game24"
    sess_id = persist_session_from_id(db=db, game_id=GAME24_ID, game_slug=GAME24_SLUG, state=state, summary=snap)
    # reset
    reset_runtime_state(state)
    # home
    return jsonify({"ok": True, "redirect_url": _home_url()}), 200

# -----------------------------------------------------------------------------
# (Optional) Session detail page
# -----------------------------------------------------------------------------
@bp.get("/session")
def session_detail():
    state = _state()
    _debug_sid("session_detail")
    snap = _build_summary(state)
    return render_template("game24/session.html", summary=snap)

# -----------------------------------------------------------------------------
# CSV export of the per_puzzle log
# -----------------------------------------------------------------------------
@bp.get("/api/export_csv")
def api_export_csv():
    state = _state()
    _debug_sid("api_export_csv")
    per = _build_summary(state)["per_puzzle"]

    buf = io.StringIO()
    logger.info("API_EXPORT_CSV Degun begin")
    w = csv.writer(buf)
    w.writerow(
        [
            "case_id",
            "level",
            "final_outcome",
            "attempts",
            "incorrect_attempts",
            "helped",
            "skipped",
            "solved",
            "started_at_ms",
            "ended_at_ms",
            # (optional) you can also add "target" here later if you want
        ]
    )
    for row in per:
        w.writerow(
            [
                row.get("case_id"),
                row.get("level"),
                row.get("final_outcome"),
                row.get("attempts"),
                row.get("incorrect_attempts"),
                int(bool(row.get("helped"))),
                int(bool(row.get("skipped"))),
                int(bool(row.get("solved"))),
                row.get("started_at_ms"),
                row.get("ended_at_ms"),
            ]
        )

    csv_text = buf.getvalue()
    lines = csv_text.splitlines()
    logger.info("[export_csv] bytes=%d lines=%d", len(csv_text.encode("utf-8")), len(lines))
    if lines:
        logger.info("[export_csv] header: %s", lines[0])
    logger.debug("[export_csv] first 5 lines:\n%s", "\n".join(lines[:5]))

    csv_bytes = buf.getvalue().encode("utf-8")
    resp = make_response(csv_bytes)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=game24_session.csv"
    return resp

# -----------------------------------------------------------------------------
# Pool config endpoints (unchanged, except they now carry state["target"] implicitly)
# -----------------------------------------------------------------------------
@bp.post("/api/pool")
def api_pool():
    state = _state()
    _debug_sid("api_pool")
    data = request.get_json(force=True) or {}

    mode = (data.get("mode") or "").strip().lower()
    if mode not in ("custom", "competition", "off"):
        return jsonify({"ok": False, "reason": "mode must be 'custom', 'competition', or 'off'"}), 400

    if mode == "off":
        p = _pool(state)
        p.update({"mode": None, "ids": [], "index": 0, "status": {}, "score": {}, "done": False})
        state["help_disabled"] = False
        state["competition_ends_at"] = None
        return jsonify({"ok": True, "mode": None, "count": 0, "time_left": None, "help_disabled": False}), 200

    raw_ids = data.get("case_ids") or data.get("ids") or data.get("puzzles") or []
    if isinstance(raw_ids, str):
        try:
            raw_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
        except ValueError:
            raw_ids = []

    case_ids: List[int] = []
    seen = set()
    store = get_store()
    for x in raw_ids:
        try:
            n = int(x)
        except (ValueError, TypeError):
            continue
        if n < 1 or n in seen:
            continue
        if store.get_by_id(n) is not None:
            seen.add(n)
            case_ids.append(n)

    if not case_ids:
        return jsonify({"ok": False, "reason": "No valid case IDs provided"}), 200

    p = _pool(state)
    p.update({"mode": mode, "ids": case_ids, "index": 0, "status": {}, "score": {}, "done": False})

    dur = data.get("duration_sec") or data.get("duration_seconds") or data.get("duration") or 0
    try:
        dur = int(dur)
    except (ValueError, TypeError):
        dur = 0

    if mode == "competition":
        if dur <= 0:
            dur = 600
        state["help_disabled"] = True
        state["competition_ends_at"] = time.time() + dur
        tleft = competition_time_left(state)
    else:
        state["help_disabled"] = False
        state["competition_ends_at"] = None
        tleft = None

    return jsonify(
        {"ok": True, "mode": mode, "count": len(case_ids), "time_left": tleft, "help_disabled": state["help_disabled"]}
    ), 200

@bp.get("/api/pool/debug")
def api_pool_debug():
    state = _state()
    _debug_sid("api_pool_debug")
    p = _pool(state)
    return jsonify(
        {
            "ok": True,
            "mode": p.get("mode"),
            "ids": p.get("ids"),
            "index": p.get("index"),
            "done": p.get("done"),
            "status": p.get("status"),
            "score": p.get("score"),
            "help_disabled": state.get("help_disabled"),
            "competition_ends_at": state.get("competition_ends_at"),
            "time_left": competition_time_left(state),
        }
    ), 200

@bp.get("/api/pool/status")
def api_pool_status():
    state = _state()
    _debug_sid("api_pool_status")
    p = _pool(state)
    if not p.get("mode"):
        return jsonify({"ok": True, "mode": None, "status": "not_in_pool"}), 200

    store = get_store()
    items = []
    for cid in p["ids"]:
        puzzle = store.get_by_id(cid)
        status_info = p["status"].get(str(cid), {"status": "unseen", "attempts": 0})
        items.append(
            {
                "case_id": cid,
                "level": puzzle.get("level") if puzzle else "unknown",
                "status": status_info["status"],
                "attempts": status_info["attempts"],
                "solved": p["score"].get(str(cid), 0) == 1,
            }
        )

    return jsonify(
        {
            "ok": True,
            "mode": p["mode"],
            "total": len(p["ids"]),
            "current_index": p["index"],
            "done": p["done"],
            "time_left": competition_time_left(state),
            "help_disabled": state.get("help_disabled", False),
            "items": items,
        }
    ), 200

@bp.get("/api/debug/store")
def api_debug_store():
    store = get_store()
    return jsonify(
        {
            "loaded_from": store.loaded_from,
            "total_puzzles": len(store.by_id),
            "pools": store.pool_report(),
            "has_data": bool(store.by_id),
        }
    )

@bp.before_request
def ensure_store_loaded():
    store = get_store()
    if not store.by_id:
        store.load(force=True)

