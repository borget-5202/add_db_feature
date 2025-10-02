# app/games/sum_4_cards/sum4_routes.py
from __future__ import annotations
import time, json, secrets, logging
from typing import List, Dict, Any, Optional

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

logger = logging.getLogger(__name__)
GAME_KEY = "sum_4_cards"

# ---------------- Runtime session state (in-memory, per session_id) ----------------
SESSIONS: Dict[str, Dict[str, Any]] = {}

def _sid() -> str:
    return get_or_create_session_id(request)

def _state() -> Dict[str, Any]:
    # baseline state every game can share (played/solved/time/etc)
    st = SESSIONS.setdefault(_sid(), default_state())
    # ensure sum4-specific keys exist
    st.setdefault("per_puzzle", [])
    st.setdefault("current_hand", None)
    st.setdefault("pool", {"mode": None, "ids": [], "index": 0, "done": False})
    return st

def _now_ms() -> int:
    return int(time.time() * 1000)

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
    if case_id is None:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k
          AND (:diff IS NULL OR v.tags->>'difficulty' = :diff)
          AND v.is_active = true
        ORDER BY random()
        LIMIT 1
        """
        row = db.session.execute(text(sql), {"k": GAME_KEY, "diff": difficulty}).mappings().first()
    else:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k AND v.case_id = :cid
        """
        row = db.session.execute(text(sql), {"k": GAME_KEY, "cid": case_id}).mappings().first()
    if not row:
        raise RuntimeError(f"No puzzle found for {GAME_KEY} (case_id={case_id}, diff={difficulty}).")
    return dict(row)

# ---------------- Reveal groups ----------------
MODE_MAP = {
    "two_then_one": [[0,1],[2],[3]],   # 2 at start → 1 → 1
    "one_by_one":   [[0],[1],[2],[3]],
    "all":          [[0,1,2,3]],
}

def _groups_from_meta(game_meta: Optional[dict]) -> List[List[int]]:
    default = MODE_MAP["two_then_one"]
    try:
        reveal = (game_meta or {}).get("reveal") or {}
        groups = reveal.get("groups")
        if isinstance(groups, list) and all(isinstance(g, list) for g in groups):
            return groups
    except Exception:
        pass
    return default

def _target_for_step(ranks: List[int], step: int, groups: List[List[int]]) -> int:
    seen = set()
    for i in range(step + 1):
        for slot in groups[i]:
            seen.add(slot)
    return sum(int(ranks[s]) for s in sorted(seen))

def _envelope(
    game: Dict[str, Any],
    case: Dict[str, Any],
    session_sid: str,
    groups_override: Optional[List[List[int]]] = None
) -> Dict[str, Any]:
    ranks: List[int] = [int(x) for x in case["ranks"]]
    groups = groups_override or _groups_from_meta(game.get("metadata"))
    init_reveal = groups[0] if groups else []
    return {
        "session_sid": session_sid,
        "game_key": GAME_KEY,
        "title": game["title"],
        "case_id": case["case_id"],
        "reveal_mode": "server",
        "table": {
            "slots": 4,
            "layout": [0,1,2,3],
            "cards": [
                {"id":"c0","rank":ranks[0],"visible": False,"face":"front"},
                {"id":"c1","rank":ranks[1],"visible": False,"face":"front"},
                {"id":"c2","rank":ranks[2],"visible": False,"face":"front"},
                {"id":"c3","rank":ranks[3],"visible": False,"face":"front"},
            ],
            "deck":[]
        },
        "reveal": {"groups": groups, "server_step": 0, "init_reveal": init_reveal},
        "grading":{"type":"sum_progressive"},
        "ui_hints":{"pace":"normal","audio_cues":False,"show_back_card":False},
        "_state":{"start_ms": _now_ms()}
    }

# ---------------- Hand bookkeeping ----------------
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
    }
    # Count played once per dealt hand
    st = state.setdefault("stats", {})
    st["played"] = int(st.get("played", 0)) + 1

def _mark_attempt(state: Dict[str, Any], ok: bool) -> None:
    cur = state.get("current_hand")
    if not cur: return
    cur["attempts"] = int(cur.get("attempts", 0)) + 1
    if not ok:
        cur["incorrect_attempts"] = int(cur.get("incorrect_attempts", 0)) + 1
        s = state.setdefault("stats", {})
        s["answer_wrong"] = int(s.get("answer_wrong", 0)) + 1
    else:
        s = state.setdefault("stats", {})
        s["answer_correct"] = int(s.get("answer_correct", 0)) + 1

def _mark_help(state: Dict[str, Any]) -> None:
    cur = state.get("current_hand")
    if not cur: return
    cur["helped"] = True
    s = state.setdefault("stats", {})
    s["help_all"] = int(s.get("help_all", 0)) + 1  # keep same counter name used by DB summary

def _finalize_hand(state: Dict[str, Any], *, solved: bool, outcome: str) -> None:
    cur = state.get("current_hand")
    if not cur: return
    cur["solved"] = bool(solved)
    cur["final_outcome"] = outcome
    cur["ended_at_ms"] = cur.get("ended_at_ms") or _now_ms()
    # Tally top-line stats
    s = state.setdefault("stats", {})
    if solved:
        s["solved"] = int(s.get("solved", 0)) + 1
    # append to per_puzzle and clear
    state.setdefault("per_puzzle", []).append(dict(cur))
    state["current_hand"] = None

def _reset_runtime_state(state: Dict[str, Any]) -> None:
    # Keep identity-ish things if you later add them; for now we reset all gameplay
    new = default_state()
    # Preserve pool config across sessions if you prefer; here we clear it:
    new["pool"] = {"mode": None, "ids": [], "index": 0, "done": False}
    SESSIONS[_sid()] = new

# ---------------- Routes ----------------
@bp.get("/play")
def play():
    game = _fetch_game_row()
    # NEW: pick up initial config from query params for shareable links
    initial_cfg = {
        "case_id": request.args.get("case_id"),             # e.g., /play?case_id=123
        "difficulty": (request.args.get("difficulty") or "").strip().lower() or None,
        "reveal": (request.args.get("reveal") or "").strip() or None,  # 'all'|'one_by_one'|'two_then_one'
        "autodeal": request.args.get("autodeal") in ("1", "true", "yes"),
    }
    return render_template("sum_4_cards/sum4_play.html",
                           game=game, game_key=GAME_KEY,
                           initial_cfg=initial_cfg)


@bp.post("/api/start")
def api_start():
    data = request.get_json(silent=True) or {}
    case_id = data.get("case_id")
    difficulty = (data.get("difficulty") or "").strip().lower() or None
    chosen_mode = (data.get("reveal_mode") or "").strip()

    game = _fetch_game_row()
    case = _fetch_case(case_id, difficulty=difficulty)

    # cookie-style sid
    try:
        session_sid = get_or_create_session_id(request)
    except Exception:
        session_sid = request.cookies.get("session_id") or secrets.token_hex(16)

    # begin/replace current hand in server state
    st = _state()
    _begin_hand(st, case_id=case["case_id"], difficulty=difficulty)

    groups = MODE_MAP.get(chosen_mode)  # None => fall back to DB
    env = _envelope(game, case, session_sid, groups_override=groups)
    env["help_disabled"] = bool(_state().get("help_disabled", False))  # NEW
    env["difficulty"] = difficulty or "auto"

    resp = make_response(jsonify({"ok": True, "envelope": env}))
    if not request.cookies.get("session_id"):
        # consistency with game_core helper naming
        resp.set_cookie("session_id", session_sid, max_age=60*60*24*365, samesite="Lax")
    return resp

@bp.post("/api/step")
def api_step():
    """
    Progressive gating:
      - {"server_step": n, "answer": 23, "envelope": {...}}
      - {"server_step": n, "action":"help", "envelope": {...}}
    """
    payload = request.get_json(silent=True) or {}
    server_step = int(payload.get("server_step", 0))
    action = payload.get("action", "answer")
    env = payload.get("envelope") or {}
    ranks = [c.get("rank") for c in (env.get("table", {}).get("cards") or [])]
    if not ranks or len(ranks) < 4:
        return jsonify({"ok": False, "error": "missing_ranks"}), 400

    groups = (env.get("reveal") or {}).get("groups") or [[0,1],[2],[3]]
    if server_step < 0 or server_step >= len(groups):
        return jsonify({"ok": True, "reveal": [], "server_step": server_step, "done": True})

    current_target = _target_for_step(ranks, server_step, groups)

    st = _state()

    if action == "help":
        _mark_help(st)
        return jsonify({"ok": True, "help": True, "expected": int(current_target), "server_step": server_step, "done": False})

    # answer flow
    if "answer" not in payload:
        return jsonify({"ok": False, "error": "missing_answer"}), 400

    val = int(payload.get("answer"))
    correct = (int(val) == int(current_target))
    _mark_attempt(st, correct)

    if not correct:
        return jsonify({"ok": True, "correct": False, "server_step": server_step, "done": False})

    next_step = server_step + 1
    if next_step >= len(groups):
        # final stage correct
        return jsonify({"ok": True, "correct": True, "reveal": [], "server_step": next_step, "done": True, "expected": int(current_target)})

    return jsonify({"ok": True, "correct": True, "reveal": groups[next_step], "server_step": next_step, "done": False})

@bp.post("/api/finish")
def api_finish():
    """
    After final correct; persists one play row in app.game_sessions summary_json (session-level).
    """
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case_id")
    final_answer = payload.get("final_answer")
    help_count = int(payload.get("help_count") or 0)

    if final_answer is None:
        return jsonify({"ok": False, "error": "missing_final_answer"}), 400

    case = _fetch_case(case_id)
    ranks = [int(x) for x in case["ranks"]]
    target = int(case["sum_pips"])
    is_correct = (int(final_answer) == target)

    # update server runtime hand
    st = _state()
    _finalize_hand(st, solved=is_correct, outcome=("solved" if is_correct else "incorrect"))

    # build a compact summary for DB
    summary = {
        "game_key": GAME_KEY,
        "per_puzzle": st.get("per_puzzle", [])[:],  # include current session’s plays so far
        "totals": {
            "played": st.get("stats", {}).get("played", 0),
            "solved": st.get("stats", {}).get("solved", 0),
            "help_all": st.get("stats", {}).get("help_all", 0),
            "answer_wrong": st.get("stats", {}).get("answer_wrong", 0),
        },
    }

    g = _fetch_game_row()
    game_id = int(g["id"])
    # Persist one session snapshot (like Game24)
    try:
        persist_session_from_id(db=db, game_id=game_id, game_key=GAME_KEY, state=st, summary=summary)
    except Exception as e:
        current_app.logger.exception("persist failed: %s", e)
        return jsonify({"ok": False, "error": "persist_failed"}), 500

    return jsonify({"ok": True, "correct": is_correct, "expected": target})

# ---------------- Summary / Exit / Pool (server-side, Game24-style) ----------------
def _summary_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """Small, readable summary like Game24 (totals + per-puzzle list)."""
    per = state.get("per_puzzle", [])[:]
    cur = state.get("current_hand")
    if cur and not cur.get("final_outcome"):
        tmp = dict(cur)
        tmp["final_outcome"] = "unsolved_exit"
        tmp["ended_at_ms"] = tmp.get("ended_at_ms") or _now_ms()
        per.append(tmp)

    totals = {"solved": 0, "helped": 0, "incorrect": 0, "skipped": 0}
    for r in per:
        if r.get("solved"): totals["solved"] += 1
        if r.get("helped"): totals["helped"] += 1
        if r.get("final_outcome") == "incorrect": totals["incorrect"] += 1
        if r.get("skipped"): totals["skipped"] += 1

    # pretty text (mono) like Game24
    lines = []
    lines.append("Totals")
    lines.append(f"  solved:   {totals['solved']}")
    lines.append(f"  helped:   {totals['helped']}")
    lines.append(f"  incorrect:{totals['incorrect']}")
    lines.append(f"  skipped:  {totals['skipped']}")
    lines.append("")
    lines.append("Actions")
    for r in per:
        cid = int(r.get("case_id") or 0)
        att = int(r.get("attempts") or 0)
        helped = "yes" if r.get("helped") else "no"
        solved = "yes" if r.get("solved") else "no"
        out = (r.get("final_outcome") or "-")
        lines.append(f"  #{cid:<4} attempts={att:<2} helped={helped:<3} solved={solved:<3} outcome={out}")

    return {
        "totals": totals,
        "per_puzzle": per,
        "report_html": "<pre>" + "\n".join(lines) + "</pre>",
    }

@bp.post("/api/summary")
def api_summary():
    st = _state()
    snap = _summary_snapshot(st)
    return jsonify({"ok": True, "stats": st.get("stats"), "play_summary": snap}), 200

@bp.post("/api/exit")
def api_exit():
    """
    Finalize current hand (as unsolved if in-progress), persist the session,
    then reset the runtime state and return a redirect URL.
    """
    st = _state()
    if st.get("current_hand"):
        _finalize_hand(st, solved=False, outcome="unsolved_exit")
    # Persist session snapshot
    g = _fetch_game_row()
    summary = _summary_snapshot(st)
    try:
        persist_session_from_id(db=db, game_id=int(g["id"]), game_key=GAME_KEY, state=st, summary=summary)
    except Exception as e:
        current_app.logger.exception("persist on exit failed: %s", e)
    # Reset for next time
    _reset_runtime_state(st)
    # Send a home URL like Game24
    try:
        home = url_for("home.index")
    except Exception:
        home = "/"
    return jsonify({"ok": True, "redirect_url": home}), 200

@bp.post("/api/pool")
def api_pool():
    """
    Store pool config in server state (custom/competition/off) with ids and timer.
    Body:
      { "mode": "custom"|"competition"|"off", "case_ids": [..] | "1,2,3", "minutes": 5 }
    """
    st = _state()
    data = request.get_json(force=True) or {}
    mode = (data.get("mode") or "").strip().lower()

    if mode not in ("custom", "competition", "off"):
        return jsonify({"ok": False, "reason": "mode must be 'custom', 'competition', or 'off'"}), 400

    p = st.setdefault("pool", {"mode": None, "ids": [], "index": 0, "done": False})

    if mode == "off":
        p.update({"mode": None, "ids": [], "index": 0, "done": False})
        st["help_disabled"] = False
        st["competition_ends_at"] = None
        return jsonify({"ok": True, "mode": None, "count": 0, "time_left": None, "help_disabled": False}), 200

    raw_ids = data.get("case_ids") or data.get("ids") or data.get("puzzles") or []
    if isinstance(raw_ids, str):
        try:
            raw_ids = [int(x.strip()) for x in raw_ids.replace("|", ",").replace(" ", ",").split(",") if x.strip()]
        except ValueError:
            raw_ids = []

    # validate & clamp list
    ids: List[int] = []
    seen = set()
    for x in raw_ids:
        try:
            n = int(x)
        except Exception:
            continue
        if n < 1 or n > 1820 or n in seen:
            continue
        seen.add(n)
        ids.append(n)
        if len(ids) >= 25: break

    p.update({"mode": mode, "ids": ids, "index": 0, "done": False})

    # competition extras
    time_left = None
    if mode == "competition":
        mins = max(1, min(60, int(data.get("minutes") or 5)))
        st["competition_ends_at"] = int(time.time() + mins * 60)
        st["help_disabled"] = True
        time_left = mins * 60
    else:
        st["competition_ends_at"] = None
        st["help_disabled"] = False

    return jsonify({"ok": True, "mode": mode, "count": len(ids), "time_left": time_left, "help_disabled": st.get("help_disabled", False)}), 200

# -------- CSV Export (current session or last persisted) --------
import csv, io, datetime

def _ms_to_iso(ms: Optional[int]) -> str:
    if not ms:
        return ""
    # ISO8601 in UTC (e.g., 2025-09-29T17:45:12Z)
    return datetime.datetime.utcfromtimestamp(ms / 1000.0).replace(microsecond=0).isoformat() + "Z"

@bp.get("/api/export.csv")
def api_export_csv():
    """
    CSV export of per-puzzle rows.
    By default uses the in-memory *current* session.
    If ?persisted=1 is passed, tries the most recent persisted summary for this sid+game.
    Columns:
      session_sid,case_id,difficulty,attempts,incorrect_attempts,helped,solved,outcome,started_at,ended_at,duration_ms
    """
    sid = _sid()
    use_persisted = request.args.get("persisted") in ("1", "true", "yes")

    rows = None
    if use_persisted:
        try:
            g = _fetch_game_row()
            rec = db.session.execute(
                text("""
                    SELECT summary_json
                    FROM app.game_sessions
                    WHERE game_id = :gid AND session_sid = :sid
                    ORDER BY id DESC
                    LIMIT 1
                """),
                {"gid": int(g["id"]), "sid": sid},
            ).first()
            if rec and rec[0]:
                per = (rec[0] or {}).get("per_puzzle") or []
                rows = per
        except Exception as e:
            current_app.logger.exception("export persisted failed: %s", e)

    if rows is None:
        st = _state()
        rows = st.get("per_puzzle", [])[:]
        # include an in-progress hand as an unsolved record (like summary)
        cur = st.get("current_hand")
        if cur and not cur.get("final_outcome"):
            tmp = dict(cur)
            tmp["final_outcome"] = "in_progress"
            tmp["ended_at_ms"] = tmp.get("ended_at_ms") or _now_ms()
            rows.append(tmp)

    # Build CSV
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "session_sid","case_id","difficulty","attempts","incorrect_attempts",
        "helped","solved","outcome","started_at","ended_at","duration_ms"
    ])
    for r in rows:
        start = r.get("started_at_ms")
        end   = r.get("ended_at_ms")
        dur   = (int(end) - int(start)) if (start and end) else ""
        w.writerow([
            sid,
            r.get("case_id") or "",
            (r.get("difficulty") or "auto"),
            int(r.get("attempts") or 0),
            int(r.get("incorrect_attempts") or 0),
            1 if r.get("helped") else 0,
            1 if r.get("solved") else 0,
            r.get("final_outcome") or "",
            _ms_to_iso(start),
            _ms_to_iso(end),
            dur
        ])

    csv_data = buf.getvalue()
    fn = f"sum4_session_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    resp = make_response(csv_data)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


@bp.post("/api/state")
def api_state():
    st = _state()
    pool = st.get("pool") or {"mode": None, "ids": [], "index": 0, "done": False}
    ends = st.get("competition_ends_at")
    time_left = None
    if ends:
      time_left = max(0, int(ends - time.time()))
    return jsonify({
        "ok": True,
        "pool": pool,
        "help_disabled": bool(st.get("help_disabled", False)),
        "time_left": time_left
    })


@bp.post("/api/skip")
def api_skip():
    st = _state()
    cur = st.get("current_hand")
    if not cur:
        return jsonify({"ok": False, "error": "no_active_hand"}), 400
    cur["skipped"] = True
    # count skipped in stats, finalize
    s = st.setdefault("stats", {})
    s["skipped"] = int(s.get("skipped", 0)) + 1
    _finalize_hand(st, solved=False, outcome="skipped")
    return jsonify({"ok": True})


