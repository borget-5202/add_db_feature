# app/games/game24/game24_routes.py
from __future__ import annotations
from typing import Dict, Any, List
import logging, time, uuid, ast, operator

from flask import (
    Blueprint, render_template, request, jsonify, make_response,
    url_for, redirect
)
from flask_login import login_required, current_user

from app.db import db
try:
    from app.models import Game, Session as GameSession
except Exception:
    from app.models import Game, GameSession  # type: ignore

from app.games.core.game_core import (
    values_key, normalize_level, rank_code, card_images,
    default_state, stats_payload, ensure_played_once, start_timer, add_elapsed,
    normalize_rank_expr,
)
from app.games.core.puzzle_store_game24 import get_store, warmup_store

logger = logging.getLogger(__name__)

bp = Blueprint(
    "game24",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/games/game24/static",
    url_prefix="/games/game24",
)

# In-memory per-tab
SESSIONS: Dict[str, Dict[str, Any]] = {}

def _sid_cookie() -> str:
    return request.cookies.get("db_session_id") or "anon"

def _state() -> Dict[str, Any]:
    sid = _sid_cookie()
    if sid not in SESSIONS:
        SESSIONS[sid] = default_state()
    return SESSIONS[sid]

# ------- safe expression evaluation -------
_ALLOWED = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow,  ast.USub: operator.neg, ast.UAdd: lambda x: x,
}

def _safe_eval(node):
    if isinstance(node, ast.Num):  # py<=3.7
        return node.n
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):  # py3.8+
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    raise ValueError("disallowed")

def _collect_expr_info(expr_src: str):
    try:
        tree = ast.parse(expr_src, mode="eval")
    except Exception:
        return False, None, [], None, "parse_error"

    class _Find(ast.NodeVisitor):
        def __init__(self):
            self.names = []
            self.numbers = []
        def visit_Name(self, node):
            self.names.append(node.id)
        def visit_Constant(self, node):
            if isinstance(node.value, (int, float)):
                v = node.value
                if isinstance(v, float) and v.is_integer():
                    v = int(v)
                self.numbers.append(abs(int(v)))
        def visit_Num(self, node):
            v = node.n
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            self.numbers.append(abs(int(v)))

    fv = _Find()
    fv.visit(tree)

    if fv.names:
        return False, None, fv.numbers, fv.names[0], None

    try:
        val = _safe_eval(tree.body)
    except Exception:
        return False, None, fv.numbers, None, "disallowed"

    if isinstance(val, float) and abs(round(val) - val) < 1e-9:
        val = int(round(val))
    return True, val, fv.numbers, None, None

# ------- routes -------
@bp.get("/")
def index():
    return redirect(url_for("game24.play"))

@bp.get("/play")
@login_required
def play():
    warmup_store(force=False)

    game = Game.query.filter_by(slug="game24").first()
    if not game:
        game = Game(slug="game24", title="24-Point Card Game", modality="cards", subject="math")
        db.session.add(game)
        db.session.flush()

    sess = GameSession(
        session_uuid=uuid.uuid4(),
        user_id=getattr(current_user, "id", None),
        game_id=game.game_id,
        started_at=None,
        completed=False,
        meta={},
    )
    db.session.add(sess)
    db.session.commit()

    level = (request.args.get("level") or "medium").lower()
    state = _state()
    store = get_store()

    puz, pool_done = store.random_pick(level, state["recent_keys"])
    if puz:
        state["recent_keys"].append(values_key(puz["cards"]))
        state["current_case_id"] = puz["case_id"]
        start_timer(state)
        state["counted_this_puzzle"] = False

    payload = {
        "ok": True,
        "seq": 0,
        "case_id": puz["case_id"] if puz else None,
        "difficulty": normalize_level(level),
        "question": puz["cards"] if puz else [],
        "values": puz["cards"] if puz else [],
        "images": card_images(puz["cards"]) if puz else [],
        "pool_done": pool_done,
        "stats": stats_payload(state),
    }

    api_base = url_for("game24.api_next").rsplit("/", 1)[0]
    resp = make_response(render_template(
        "play.html",
        title=game.title,
        game24_api_base=api_base,
        first_payload=payload
    ))
    resp.set_cookie("db_session_id", str(sess.id), httponly=True, samesite="Lax", path="/")
    if not request.cookies.get("session_id"):
        resp.set_cookie("session_id", str(sess.session_uuid), samesite="Lax", path="/")
    return resp

@bp.get("/api/pool_report")
def api_pool_report():
    store = get_store()
    return jsonify({"ok": True, "pools": store.pool_report(), "stats": stats_payload(_state())})

@bp.get("/api/next")
def api_next():
    level = (request.args.get("level") or "medium").lower()
    seq   = int(request.args.get("seq") or 0)
    state = _state()
    store = get_store()

    puz, pool_done = store.random_pick(level, state["recent_keys"])
    if puz:
        state["recent_keys"].append(values_key(puz["cards"]))
        if len(state["recent_keys"]) > 100:
            state["recent_keys"] = state["recent_keys"][-100:]
        state["current_case_id"] = puz["case_id"]
        start_timer(state)
        state["counted_this_puzzle"] = False

    return jsonify({
        "ok": True,
        "seq": seq,
        "case_id": puz["case_id"] if puz else None,
        "difficulty": normalize_level(level),
        "question": puz["cards"] if puz else [],
        "values": puz["cards"] if puz else [],
        "images": card_images(puz["cards"]) if puz else [],
        "pool_done": pool_done,
        "stats": stats_payload(state),
    }), 200

@bp.post("/api/check")
def api_check():
    j = request.get_json(silent=True) or {}
    logger.debug("api_check: raw json: %r", j)

    # accept all historical keys
    expr_src = (j.get("expr") or j.get("expression") or j.get("answer") or "").strip()
    values   = j.get("values") or j.get("cards") or []
    logger.debug("api_check: expr_src=%r values=%r", expr_src, values)
    expr_src = normalize_rank_expr(expr_src)

    state = _state()
    state["stats"]["answer_attempts"] += 1
    ensure_played_once(state)

    # normalize target multiset
    try:
        target_multiset = sorted(int(x) for x in values)
    except Exception:
        target_multiset = []

    ok_parse, val, nums_used, unknown, err = _collect_expr_info(expr_src)
    logger.debug("api_check: parsed ok=%s val=%r nums=%r unknown=%r err=%r",
                 ok_parse, val, nums_used, unknown, err)

    if unknown:
        state["stats"]["answer_wrong"] += 1
        return jsonify({"ok": False,
                        "reason": f"Unknown identifier: {unknown}",
                        "stats": stats_payload(state)}), 200

    if not ok_parse:
        state["stats"]["answer_wrong"] += 1
        return jsonify({"ok": False,
                        "reason": "Try again!",
                        "stats": stats_payload(state)}), 200

    # compare numeric-literal multiset against provided values
    try:
        used_multiset = sorted(int(x) for x in nums_used)
    except Exception:
        used_multiset = []

    if len(target_multiset) == 4 and used_multiset != target_multiset:
        state["stats"]["answer_wrong"] += 1
        return jsonify({"ok": False,
                        "reason": "Must use all 4 input numbers exactly once",
                        "stats": stats_payload(state)}), 200

    # check result
    is_24 = (val is not None) and (abs(float(val) - 24.0) < 1e-6)
    if is_24:
        state["stats"]["answer_correct"] += 1
        state["stats"]["solved"] += 1
        add_elapsed(state)
        return jsonify({"ok": True, "stats": stats_payload(state)}), 200

    # wrong result
    state["stats"]["answer_wrong"] += 1

    # show solvable hint on 2nd+ wrong attempt if we have stored solutions
    solvable = False
    try:
        store = get_store()
        puz = store.get_by_values(values) if values else None
        solvable = bool(puz and puz.get("solutions"))
    except Exception:
        pass

    wrong_count = state["stats"]["answer_wrong"]
    shown = int(val) if isinstance(val, int) else (round(val, 6) if isinstance(val, float) else val)
    reason = ("Incorrect — this case is solvable. Try Help to see one"
              if wrong_count >= 2 and solvable
              else f"Try again! (got {shown})")

    logger.debug("api_check send to frontend: raw stats_payload: %r", stats_payload(state))
    return jsonify({"ok": False, "reason": reason, "stats": stats_payload(state)}), 200


@bp.post("/api/help")
def api_help():
    j = request.get_json(silent=True) or {}
    values = j.get("values") or []
    state  = _state()

    store = get_store()
    puz = store.get_by_values(values) if values else None

    ensure_played_once(state)
    state["stats"]["revealed"] += 1
    add_elapsed(state)

    sols = puz.get("solutions") if puz else []
    return jsonify({"ok": True, "has_solution": bool(sols), "solutions": sols, "stats": stats_payload(state)}), 200

@bp.post("/api/restart")
def api_restart():
    sid = _sid_cookie()
    if sid in SESSIONS:
        del SESSIONS[sid]
    return jsonify({"ok": True, "stats": stats_payload(default_state())}), 200

@bp.post("/api/exit")
def api_exit():
    state = _state()
    add_elapsed(state)

    try:
        sess_id = int(_sid_cookie())
        sess = GameSession.query.get(sess_id)
        if sess:
            sess.completed = True
            meta = (sess.meta or {})
            meta["stats"] = stats_payload(state)
            sess.meta = meta
            db.session.add(sess)
            db.session.commit()
    except Exception:
        pass

    if _sid_cookie() in SESSIONS:
        del SESSIONS[_sid_cookie()]

    return jsonify({"ok": True, "next_url": url_for("home.index"), "stats": stats_payload(state)}), 200

