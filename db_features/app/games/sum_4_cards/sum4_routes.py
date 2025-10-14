# app/games/sum_4_cards/sum4_routes.py
from __future__ import annotations
import time, json, secrets, logging
from typing import List, Dict, Any, Optional
import random

from flask import request, render_template, jsonify, current_app, make_response, url_for
from sqlalchemy import text
from app import db
from . import bp

# Reuse shared helpers from game_core
try:
    from app.game.core.game_core import (
        default_state,
        get_or_create_session_id,
        persist_session_from_id,
    )
except Exception:
    from app.games.core.game_core import (
        default_state,
        get_or_create_session_id,
        persist_session_from_id,
    )

# =======================
# DEBUG SWITCH + LOGGER
# =======================
DEBUG_SUM4 = True
logger = logging.getLogger("sum4")
logger.setLevel(logging.INFO)

def dbg(*args, **kwargs):
    if DEBUG_SUM4:
        try:
            logger.info(" ".join(str(a) for a in args))
        except Exception:
            print("[SUM4]", *args)

GAME_KEY = "sum_4_cards"

# ---------------- Runtime session state ----------------
SESSIONS: Dict[str, Dict[str, Any]] = {}

def _sid() -> str:
    return get_or_create_session_id(request)

def _now_ms() -> int:
    return int(time.time() * 1000)

def _fmt_mmss(ms: int) -> str:
    s = int((ms or 0)/1000); m = s//60; r = s%60
    return f"{m:02d}:{r:02d}"

def _state() -> Dict[str, Any]:
    st = SESSIONS.setdefault(_sid(), default_state())

    # Session context
    st.setdefault("session_context", {
        "type": "single",     # "single", "pool_custom", "pool_competition"
        "pool_id": None,
        "started_at": _now_ms()
    })

    # Overall session stats (persist across puzzles until user resets)
    st.setdefault("overall_stats", {
        "played": 0, "solved": 0,
        "helped": 0, "incorrect": 0, "skipped": 0,
        "total_time_ms": 0, "total_attempts": 0,
        "correct_steps": 0
    })

    # Also expose "stats" as an alias for compatibility with older code
    st.setdefault("stats", st["overall_stats"])

    # Pool stats (we also keep pool["stats"], this is auxiliary)
    st.setdefault("pool_stats", {
        "played": 0, "solved": 0,
        "helped": 0, "incorrect": 0, "skipped": 0,
        "total_time_ms": 0, "total_attempts": 0,
        "correct_steps": 0
    })

    # Pool state
    st.setdefault("pool", {
        "mode": None,       # None / "custom" / "competition"
        "ids": [],
        "completed": set(),
        "start_time": None,
        # pool["stats"] is created/updated when pool runs
    })

    # History of puzzles in this session (for modal)
    st.setdefault("history", [])
    # Per-puzzle snapshots (legacy use; we still append finalized hands)
    st.setdefault("per_puzzle", [])
    st.setdefault("current_hand", None)

    if "session_start_ms" not in st:
        st["session_start_ms"] = _now_ms()

    return st

def _fetch_game_row() -> Dict[str, Any]:
    row = db.session.execute(
        text("SELECT id, title, metadata FROM app.games WHERE game_key=:k"),
        {"k": GAME_KEY},
    ).mappings().first()
    if not row:
        raise RuntimeError(f"Game {GAME_KEY} not found.")
    return dict(row)

# ---------------- Puzzle fetch ----------------
def _fetch_case(case_id: Optional[int] = None, difficulty: Optional[str] = None) -> Dict[str, Any]:
    dbg("DEBUG: _fetch_case:", GAME_KEY, "case_id=", case_id, "difficulty=", difficulty)
    if case_id is None:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k AND v.is_active = true
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

    dbg("DEBUG: Query result:", row)
    if not row:
        raise RuntimeError(f"No puzzle found for {GAME_KEY} (case_id={case_id}, diff={difficulty}).")

    result = dict(row)
    dbg("DEBUG: Returning case:", result)
    return result

# ---------------- Reveal groups ----------------
MODE_MAP = {
    "two_then_one": [[0,1],[2],[3]],
    "one_by_one": [[0],[1],[2],[3]],
    "all_at_once": [[0,1,2,3]],
}

def _target_for_step(ranks: List[int], step: int, groups: List[List[int]]) -> int:
    seen = set()
    for i in range(step + 1):
        for slot in groups[i]:
            seen.add(slot)
    return sum(int(ranks[s]) for s in sorted(seen))

def _envelope(game, case, session_sid, groups_override=None):
    ranks_orig = [int(x) for x in case["ranks"]]
    ranks_shuffled = ranks_orig[:]
    random.shuffle(ranks_shuffled)

    groups = groups_override or MODE_MAP["two_then_one"]
    init_reveal = groups[0] if groups else []

    suits = ['S', 'H', 'D', 'C']
    random.shuffle(suits)
    cards = []
    for i, r in enumerate(ranks_shuffled):
        cards.append({
            "id": f"c{i}",
            "rank": r,
            "suit": suits[i],
            "visible": False,
            "face": "front",
        })

    return {
        "session_sid": session_sid,
        "game_key": GAME_KEY,
        "title": game["title"],
        "case_id": case["case_id"],
        "reveal_mode": "server",
        "table": {
            "slots": 4,
            "layout": [0, 1, 2, 3],
            "cards": cards,
            "deck": []
        },
        "reveal": {"groups": groups, "server_step": 0, "init_reveal": init_reveal},
        "grading": {"type": "sum_progressive"},
        "ui_hints": {"pace": "normal", "audio_cues": False, "show_back_card": False},
        "_state": {"start_ms": _now_ms()},
    }

# ---------------- Pool helpers ----------------
def _get_next_pool_case(state: Dict[str, Any]) -> Optional[int]:
    pool = state.get("pool", {})
    if pool.get("mode") not in ("custom", "competition"):
        return None
    case_ids = pool.get("ids", [])
    completed = set(pool.get("completed", []))
    dbg("DEBUG NEXT CASE: case_ids=", case_ids, "completed=", completed)
    for case_id in case_ids:
        if case_id not in completed:
            dbg("DEBUG NEXT CASE: Returning", case_id)
            return case_id
    dbg("DEBUG NEXT CASE: No more cases, returning None")
    return None

def _update_pool_stats(state: Dict[str, Any], case_id: int, solved: bool, helped: bool = False):
    pool = state.get("pool", {})
    if pool.get("mode") not in ("custom", "competition"):
        return

    # Mark completion in pool
    completed = set(pool.get("completed", []))
    completed.add(int(case_id))
    pool["completed"] = list(completed)
    dbg("DEBUG UPDATE POOL: Added case", case_id, "to completed, now:", pool["completed"])

    # Maintain pool["stats"] (used by pool summary)
    pool_stats = pool.setdefault("stats", {
        "played": 0, "solved": 0, "helped": 0, "incorrect": 0, "skipped": 0,
        "total_attempts": 0, "time_ms": 0, "correct_steps": 0
    })
    pool_stats["played"] = len(completed)
    if solved:
        pool_stats["solved"] = pool_stats.get("solved", 0) + 1
    else:
        pool_stats["skipped"] = pool_stats.get("skipped", 0) + 1
    if helped:
        pool_stats["helped"] = pool_stats.get("helped", 0) + 1
    dbg("DEBUG UPDATE POOL: final pool_stats:", pool_stats)

def _get_pool_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    pool = state.get("pool", {})
    mode = pool.get("mode")
    if mode not in ("custom", "competition"):
        return {"active": False}
    case_ids = pool.get("ids", [])
    completed = set(pool.get("completed", []))
    unfinished = [cid for cid in case_ids if cid not in completed]
    return {
        "active": True,
        "mode": mode,
        "total_cases": len(case_ids),
        "completed_cases": len(completed),
        "remaining_cases": len(unfinished),
        "unfinished_cases": unfinished,
        "progress": f"{len(completed)}/{len(case_ids)}",
        "completed_list": list(completed)
    }

# ---------------- Competition Timing ----------
def _start_competition_timer(state: Dict[str, Any], minutes: int):
    state["competition_ends_at"] = _now_ms() + (minutes * 60 * 1000)
    state["competition_duration_minutes"] = minutes
    return state["competition_ends_at"]

def _get_competition_time_remaining(state: Dict[str, Any]) -> Dict[str, Any]:
    ends_at = state.get("competition_ends_at")
    if not ends_at:
        return {"active": False, "remaining_ms": 0}
    remaining_ms = max(0, ends_at - _now_ms())
    total_ms = state.get("competition_duration_minutes", 5) * 60 * 1000
    elapsed_ms = total_ms - remaining_ms
    return {"active": True, "remaining_ms": remaining_ms, "total_ms": total_ms,
            "elapsed_ms": elapsed_ms, "ends_at": ends_at}

def _is_competition_finished(state: Dict[str, Any]) -> bool:
    t = _get_competition_time_remaining(state)
    return t["active"] and t["remaining_ms"] <= 0

def _cleanup_expired_competition(state: Dict[str, Any]) -> bool:
    pool = state.get("pool", {})
    if (pool.get("mode") == "competition" and 
        _is_competition_finished(state) and
        _get_next_pool_case(state) is None):
        dbg("DEBUG: Auto-cleaning expired completed competition")
        state["competition_ends_at"] = None
        state["help_disabled"] = False
        return True
    return False

# ---------------- Hand Management ----------------
def _begin_hand(state: Dict[str, Any], *, case_id: int, difficulty: Optional[str]) -> None:
    state["current_hand"] = {
        "case_id": int(case_id),
        "difficulty": difficulty or "auto",
        "attempts": 0,
        "incorrect_attempts": 0,
        "helped": False,
        "skipped": False,
        "solved": False,
        "started_at_ms": _now_ms(),
        "ended_at_ms": None,
        "final_outcome": None,
        "is_pool_puzzle": state.get("pool", {}).get("mode") in ("custom", "competition")
    }

def _mark_attempt(state: Dict[str, Any], ok: bool) -> None:
    cur = state.get("current_hand")
    if not cur:
        return
    cur["attempts"] = cur.get("attempts", 0) + 1

    overall = state.setdefault("overall_stats", {})
    overall["total_attempts"] = overall.get("total_attempts", 0) + 1

    if not ok:
        cur["incorrect_attempts"] = cur.get("incorrect_attempts", 0) + 1
        overall["incorrect"] = overall.get("incorrect", 0) + 1
    else:
        overall["correct_steps"] = overall.get("correct_steps", 0) + 1

    if cur.get("is_pool_puzzle"):
        pstats = state.setdefault("pool_stats", {})
        pstats["total_attempts"] = pstats.get("total_attempts", 0) + 1
        if not ok:
            pstats["incorrect"] = pstats.get("incorrect", 0) + 1
        else:
            pstats["correct_steps"] = pstats.get("correct_steps", 0) + 1

def _mark_help(state: Dict[str, Any]) -> None:
    cur = state.get("current_hand")
    if not cur:
        return
    cur["helped"] = True
    overall = state.setdefault("overall_stats", {})
    overall["helped"] = overall.get("helped", 0) + 1
    if cur.get("is_pool_puzzle"):
        pstats = state.setdefault("pool_stats", {})
        pstats["helped"] = pstats.get("helped", 0) + 1

def _finalize_hand(state: Dict[str, Any], *, solved: bool, outcome: str) -> None:
    cur = state.get("current_hand")
    if not cur:
        return
    cur["solved"] = bool(solved)
    cur["final_outcome"] = outcome
    cur["ended_at_ms"] = _now_ms()

    # Duration
    start = cur.get("started_at_ms", 0)
    end   = cur.get("ended_at_ms", 0)
    dur   = end - start if end > start else 0
    cur["duration_ms"] = dur

    # Overall stats
    overall = state.setdefault("overall_stats", {})
    overall["played"] = overall.get("played", 0) + 1
    if solved:
        overall["solved"] = overall.get("solved", 0) + 1
    if cur.get("skipped"):
        overall["skipped"] = overall.get("skipped", 0) + 1
    overall["total_time_ms"] = overall.get("total_time_ms", 0) + dur

    # Pool stats (aux)
    if cur.get("is_pool_puzzle"):
        pstats = state.setdefault("pool_stats", {})
        pstats["played"] = pstats.get("played", 0) + 1
        if solved:
            pstats["solved"] = pstats.get("solved", 0) + 1
        if cur.get("skipped"):
            pstats["skipped"] = pstats.get("skipped", 0) + 1
        pstats["total_time_ms"] = pstats.get("total_time_ms", 0) + dur

    # Store snapshot
    state.setdefault("per_puzzle", []).append(dict(cur))
    state["current_hand"] = None

# ---------------- Routes ----------------
@bp.get("/play")
def play():
    game = _fetch_game_row()
    initial_cfg = {
        "case_id": request.args.get("case_id"),
        "difficulty": (request.args.get("difficulty") or "").strip().lower() or None,
        "reveal": (request.args.get("reveal") or "").strip() or None,
        "autodeal": request.args.get("autodeal") in ("1", "true", "yes"),
    }
    dbg("in sum4 card game now")
    return render_template("sum_4_cards/sum4_play.html",
                           game=game, game_key=GAME_KEY,
                           initial_cfg=initial_cfg)

@bp.post("/api/start")
def api_start():
    data = request.get_json(silent=True) or {}
    case_id = data.get("case_id")
    difficulty = (data.get("difficulty") or "").strip().lower() or None
    chosen_mode = (data.get("reveal_mode") or "").strip()
    dbg("api_start", data)

    st = _state()
    session_ctx = st["session_context"]

    dbg(f"DEBUG START: case_id={case_id}, reveal_mode={chosen_mode}, difficulty={difficulty}, pool_mode={st.get('pool', {}).get('mode')}")
    dbg("DEBUG SESSION CTX:", session_ctx)

    # Cleanup expired competition (if any)
    _cleanup_expired_competition(st)

    if _is_competition_finished(st):
        return jsonify({"ok": False, "error": "competition_finished", "message": "Competition time has expired"}), 400

    # Pool-directed case picking
    pool = st.get("pool", {})
    if case_id is None and pool.get("mode") in ("custom", "competition"):
        next_case_id = _get_next_pool_case(st)
        if next_case_id is None:
            dbg("DEBUG: Pool completed, returning success")
            pool_progress = _get_pool_progress(st)
            return jsonify({
                "ok": True,
                "pool_completed": True,
                "pool_progress": pool_progress,
                "message": "All pool cases completed - great job!"
            }), 200
        case_id = next_case_id
        session_ctx["type"] = f"pool_{pool['mode']}"
        session_ctx["pool_id"] = f"pool_{_now_ms()}"
    else:
        session_ctx["type"] = "single"
        session_ctx["pool_id"] = None
        if case_id is None:
            picked = _fetch_case(case_id=None, difficulty=difficulty)
            case_id = int(picked["case_id"])
            dbg("DEBUG PICKED RANDOM CASE_ID:", case_id, f"(difficulty={difficulty or 'auto'})")

    dbg("DEBUG FINAL CASE_ID:", case_id)
    dbg("DEBUG FINAL SESSION TYPE:", session_ctx["type"])

    # Fetch resources and begin hand
    game = _fetch_game_row()
    case = _fetch_case(case_id, difficulty=difficulty)
    session_sid = get_or_create_session_id(request)
    _begin_hand(st, case_id=case["case_id"], difficulty=difficulty)

    groups = MODE_MAP.get(chosen_mode, MODE_MAP["two_then_one"])
    env = _envelope(game, case, session_sid, groups_override=groups)

    # Competition hint lock
    if pool.get("mode") == "competition":
        env["help_disabled"] = True
        st["help_disabled"] = True
    else:
        env["help_disabled"] = False
        st["help_disabled"] = False

    # Uniform pool flags
    pool_progress = _get_pool_progress(st)
    pool_completed = pool_progress.get("active", False) and pool_progress.get("remaining_cases", 0) == 0

    resp_data = {
        "ok": True,
        "envelope": env,
        "pool_progress": pool_progress,
        "pool_completed": pool_completed,
        "time_info": _get_competition_time_remaining(st),
        "session_type": session_ctx["type"]
    }
    resp = make_response(jsonify(resp_data))

    if not request.cookies.get("session_id"):
        resp.set_cookie("session_id", session_sid, max_age=60*60*24*365, samesite="Lax")

    dbg("DEBUG API_START SESSIONID:", str(request.cookies.get("session_id")))
    return resp

@bp.post("/api/step")
def api_step():
    dbg("=== STEP ENDPOINT CALLED ===")
    payload = request.get_json(silent=True) or {}
    dbg("STEP payload:", payload)

    server_step = int(payload.get("server_step", 0))
    action = payload.get("action", "answer")
    env = payload.get("envelope") or {}
    ranks = [c.get("rank") for c in (env.get("table", {}).get("cards") or [])]
    if not ranks or len(ranks) < 4:
        return jsonify({"ok": False, "error": "missing_ranks"}), 400

    groups = (env.get("reveal") or {}).get("groups") or MODE_MAP["two_then_one"]
    if server_step < 0 or server_step >= len(groups):
        return jsonify({"ok": True, "reveal": [], "server_step": server_step, "done": True})

    current_target = _target_for_step(ranks, server_step, groups)
    st = _state()

    if action == "help":
        _mark_help(st)
        return jsonify({
            "ok": True, "help": True,
            "expected": int(current_target),
            "server_step": server_step, "done": False
        })

    if "answer" not in payload and "value" not in payload:
        return jsonify({"ok": False, "error": "missing_answer"}), 400

    val = payload.get("answer")
    if val is None and "value" in payload:
        val = payload["value"]
    try:
        val = int(val)
    except Exception:
        return jsonify({"ok": False, "error": "bad_answer"}), 400

    correct = (val == current_target)
    _mark_attempt(st, correct)

    if not correct:
        return jsonify({
            "ok": True, "correct": False,
            "expected": int(current_target),
            "server_step": server_step, "done": False
        })

    next_step = server_step + 1
    if next_step >= len(groups):
        # Finished all steps
        resp = {"ok": True, "correct": True, "reveal": [],
                "server_step": next_step, "done": True,
                "expected": int(current_target)}
        dbg("STEP response for complete", resp)
        return jsonify(resp)

    # Continue to next reveal group
    resp = {"ok": True, "correct": True, "reveal": groups[next_step],
            "server_step": next_step, "done": False,
            "expected": int(current_target)}
    dbg("STEP response for unfinished pool", resp)
    return jsonify(resp)

@bp.post("/api/finish")
def api_finish():
    payload = request.get_json(silent=True) or {}
    case_id = int(payload.get("case_id"))
    final_answer = payload.get("final_answer")
    help_count = int(payload.get("help_count") or 0)

    dbg("DEBUG FINISH: case_id=", case_id, "final_answer=", final_answer)

    if final_answer is None:
        return jsonify({"ok": False, "error": "missing_final_answer"}), 400

    case = _fetch_case(case_id)
    target = int(case["sum_pips"])
    is_correct = (int(final_answer) == target)

    st = _state()
    _finalize_hand(st, solved=is_correct, outcome=("solved" if is_correct else "incorrect"))

    # Append to session history (for modal)
    # Use the just-finalized per_puzzle entry for timings if present
    last = (st.get("per_puzzle") or [])[-1] if st.get("per_puzzle") else {}
    st.setdefault("history", []).append({
        "case_id": case_id,
        "result": "correct" if is_correct else "wrong",
        "answer": int(final_answer),
        "expected": target,
        "helps_used": 1 if help_count > 0 or last.get("helped") else 0,
        "steps": last.get("attempts", 0),   # total 'check' attempts for puzzle
        "time_ms": last.get("duration_ms", 0),
        "ts": _now_ms()
    })

    # Pool bookkeeping
    pool = st.get("pool", {})
    dbg("DEBUG FINISH: Current pool mode=", pool.get('mode'), "ids=", pool.get('ids'), "completed=", pool.get('completed'))
    if pool.get("mode") in ("custom", "competition"):
        _update_pool_stats(st, case_id, is_correct, help_count > 0)
        # Also keep a richer pool details list for the pool modal
        details = st.setdefault("pool_details", [])
        details.append({
            "case_id": case_id,
            "result": "correct" if is_correct else "wrong",
            "answer": int(final_answer),
            "expected": target,
            "helps_used": 1 if help_count > 0 or last.get("helped") else 0,
            "steps": last.get("attempts", 0),
            "time_ms": last.get("duration_ms", 0)
        })
        dbg("DEBUG FINISH: After update - completed=", pool.get('completed'))

    # Persist snapshot
    g = _fetch_game_row()
    summary = {
        "game_key": GAME_KEY,
        "per_puzzle": st.get("per_puzzle", [])[:],
        "pool_progress": _get_pool_progress(st),
        "totals": st.get("stats", {}),
    }
    try:
        persist_session_from_id(
            db=db, game_id=int(g["id"]), game_key=GAME_KEY,
            state=st, summary=summary
        )
    except Exception as e:
        current_app.logger.exception("persist failed: %s", e)
        return jsonify({"ok": False, "error": "persist_failed"}), 500

    pool_progress = _get_pool_progress(st)
    pool_completed = pool_progress.get("active", False) and pool_progress.get("remaining_cases", 0) == 0

    return jsonify({
        "ok": True, "correct": is_correct, "expected": target,
        "pool_progress": pool_progress, "pool_completed": pool_completed
    })

@bp.post("/api/skip")
def api_skip():
    st = _state()
    cur = st.get("current_hand")
    if not cur:
        return jsonify({"ok": False, "error": "no_active_hand"}), 400

    case_id = cur.get("case_id")
    cur["skipped"] = True

    # Update overall stats (alias kept in st["stats"])
    overall = st.setdefault("overall_stats", {})
    overall["skipped"] = overall.get("skipped", 0) + 1

    # Pool stats via helper
    pool = st.get("pool", {})
    if pool.get("mode") in ("custom", "competition"):
        _update_pool_stats(st, case_id, solved=False)

    _finalize_hand(st, solved=False, outcome="skipped")

    pool_progress = _get_pool_progress(st)
    pool_completed = pool_progress.get("active", False) and pool_progress.get("remaining_cases", 0) == 0

    return jsonify({"ok": True, "pool_progress": pool_progress, "pool_completed": pool_completed})

@bp.post("/api/pool")
def api_pool():
    st = _state()
    data = request.get_json(force=True) or {}
    mode = (data.get("mode") or "").strip().lower()

    dbg("DEBUG POOL API: Request mode=", mode, " data=", data)
    dbg("DEBUG POOL API: Current pool state before=", st.get("pool"))

    if mode not in ("custom", "competition", "off"):
        return jsonify({"ok": False, "reason": "mode must be 'custom', 'competition', or 'off'"}), 400

    p = st.setdefault("pool", {
        "mode": None, "ids": [], "completed": set(), "start_time": None
    })

    if mode == "off":
        dbg("DEBUG POOL API: Clearing pool mode (OFF request)")
        p.update({"mode": None, "ids": [], "completed": set(), "start_time": None})
        st["help_disabled"] = False
        st["competition_ends_at"] = None
        dbg("DEBUG POOL API: Pool state after OFF=", st.get("pool"))
        # keep pool stats/history until user starts a new pool or exits
        return jsonify({"ok": True, "mode": None}), 200

    # Parse case IDs
    raw_ids = data.get("case_ids") or data.get("ids") or []
    if isinstance(raw_ids, str):
        try:
            raw_ids = [int(x.strip()) for x in raw_ids.replace("|", ",").replace(" ", ",").split(",") if x.strip()]
        except ValueError:
            raw_ids = []

    ids: List[int] = []
    seen = set()
    for x in raw_ids:
        try:
            n = int(x)
        except Exception:
            continue
        if 1 <= n <= 1820 and n not in seen:
            seen.add(n)
            ids.append(n)
        if len(ids) >= 25:
            break

    p.update({"mode": mode, "ids": ids, "completed": set(), "start_time": _now_ms()})

    # RESET POOL STATS (aux) when starting/restarting a pool
    st["pool_stats"] = {
        "played": 0, "solved": 0, "helped": 0, "incorrect": 0,
        "skipped": 0, "total_time_ms": 0, "total_attempts": 0, "correct_steps": 0
    }
    # Clear pool_details list for new pool run
    st["pool_details"] = []

    if mode == "competition":
        mins = max(1, min(60, int(data.get("minutes") or 5)))
        _start_competition_timer(st, mins)
        st["help_disabled"] = True
        time_info = _get_competition_time_remaining(st)
    else:
        st["competition_ends_at"] = None
        st["help_disabled"] = False
        time_info = {"active": False}

    if mode in ("custom", "competition"):
        # Clear any active hand when pool switches
        st["current_hand"] = None

    return jsonify({
        "ok": True, "mode": mode, "count": len(ids),
        "progress": _get_pool_progress(st), "time_info": time_info,
        "help_disabled": st.get("help_disabled", False)
    })

@bp.get("/api/pool/progress")
def api_pool_progress():
    st = _state()
    return jsonify({"ok": True, "progress": _get_pool_progress(st)})

@bp.get("/api/competition/time")
def api_competition_time():
    st = _state()
    t = _get_competition_time_remaining(st)
    if t["active"]:
        t["remaining_formatted"] = _fmt_mmss(t["remaining_ms"])
        t["elapsed_formatted"] = _fmt_mmss(t["elapsed_ms"])
    return jsonify({"ok": True, "time_info": t})

@bp.post("/api/debug/reset")
def api_debug_reset():
    SESSIONS.clear()
    return jsonify({"ok": True, "message": "State reset"})

@bp.get("/api/debug/state")
def api_debug_state():
    st = _state()
    return jsonify({"ok": True, "debug": {
        "session_id": _sid(),
        "current_hand": st.get("current_hand"),
        "pool": st.get("pool"),
        "overall_stats": st.get("overall_stats"),
        "pool_stats": st.get("pool_stats"),
        "stats_alias": st.get("stats"),  # compatibility view
        "per_puzzle_count": len(st.get("per_puzzle", [])),
        "history_count": len(st.get("history", [])),
    }})

@bp.post("/api/summary")
def api_summary():
    st = _state()
    ctx = st["session_context"]
    overall = st.get("overall_stats", {})
    history = st.get("history", [])

    # normalize to frontend-expected keys
    stats = {
        "played": overall.get("played", 0),
        "solved": overall.get("solved", 0),
        "wrong":  overall.get("incorrect", 0),
        "helps":  overall.get("helped", 0),
        "skipped": overall.get("skipped", 0),
        "total_attempts": overall.get("total_attempts", 0),
        "time_ms": overall.get("total_time_ms", 0),
    }
    attempts = stats["solved"] + stats["wrong"]
    accuracy = round(100.0 * stats["solved"] / attempts, 1) if attempts else 0.0

    dur_ms = max(0, _now_ms() - ctx.get("started_at", _now_ms()))
    summary = {
        "type": "session",
        "session_type": ctx.get("type", "single"),
        "session_duration_ms": dur_ms,
        "session_duration_formatted": _fmt_mmss(dur_ms),
        "stats": stats,
        "accuracy_percent": accuracy,
        "total_time_formatted": _fmt_mmss(stats["time_ms"]),
        "pool_progress": {"active": bool(st.get("pool", {}).get("mode"))},
        "history": history[-20:]
    }
    dbg("SUMMARY:", summary)
    return jsonify({"ok": True, "summary": summary})

@bp.get("/api/pool_summary")
def api_pool_summary():
    st = _state()
    pool = st.get("pool", {}) or {}
    mode = pool.get("mode")
    ids = pool.get("ids", [])
    completed = pool.get("completed", [])
    pst = pool.get("stats", {})  # use pool["stats"] maintained during pool
    time_ms = pst.get("time_ms", 0)

    progress = {
        "active": bool(mode),
        "mode": mode or "off",
        "total_cases": len(ids),
        "completed_cases": len(completed),
        "remaining_cases": max(0, len(ids) - len(completed)),
        "completed_list": completed,
        "unfinished_cases": [c for c in ids if c not in completed],
    }
    stats = {
        "done": progress["completed_cases"],
        "total": progress["total_cases"],
        "correct": pst.get("solved", 0),
        "wrong": pst.get("wrong", 0),
        "skipped": pst.get("skipped", 0),
        "helps": pst.get("helped", 0),
        "time_ms": time_ms,
        "time": _fmt_mmss(time_ms),
    }
    details = st.get("pool_details", [])  # [{case_id,result,answer,expected,helps_used,steps,time_ms},...]

    payload = {"ok": True, "summary": {
        "type": "pool",
        "mode": mode or "off",
        "progress": progress,
        "stats": stats,
        "details": details
    }}
    dbg("POOL SUMMARY:", payload)
    return jsonify(payload)

