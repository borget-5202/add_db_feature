# app/games/core/game_core.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import uuid
import random
import time
import re
import logging
from flask import url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB
import json, secrets
import time, hashlib, base64, secrets, json, logging
from fractions import Fraction
from functools import lru_cache

logger = logging.getLogger(__name__)

# ============================================================
# Values / difficulty helpers
# ============================================================

def values_key(vals: List[int]) -> str:
    """
    Stable key for a hand of 4 numbers. Your current build zero-pads and sorts.
    e.g. [4, 8, 1, 8] -> "01-04-08-08"
    """
    return "-".join(f"{int(x):02d}" for x in sorted(map(int, vals or [])))

def normalize_level(level: str) -> str:
    """
    Normalizes UI level -> canonical level (supports 'all' + 'nosol' too).
    """
    level = (level or "").strip().lower()
    return level if level in ("easy", "medium", "hard", "challenge", "nosol", "all") else "medium"


# ============================================================
# Rank-letter → number normalization (A, T, J, Q, K)
# ============================================================

_RANK_TO_NUM = {"A": "1", "T": "10", "J": "11", "Q": "12", "K": "13"}
_RANK_EXPR_RE = re.compile(r"\b([ATJQK])\b", re.IGNORECASE)

def normalize_rank_expr(expr: str) -> str:
    """
    Convert rank letters to numerals before arithmetic parsing:
      'K+K-J+9' -> '13+13-11+9'
    Whole-token matches only.
    """
    if not expr:
        logger.debug("normalize_rank_expr received empty expr")
        return expr
    def repl(m: re.Match) -> str:
        return _RANK_TO_NUM[m.group(1).upper()]
    return _RANK_EXPR_RE.sub(repl, expr)


# ============================================================
# Card / image helpers
# ============================================================

_RANK = {1: "A", 10: "T", 11: "J", 12: "Q", 13: "K"}
SUITS = ("S", "H", "D", "C")

def rank_code(n: int) -> str:
    return _RANK.get(int(n), str(int(n)))

def card_image_url_from_assets(code: str) -> str:
    """
    Uses the shared assets blueprint. PNGs live at:
      games_assets_bp.static('cards/<code>.png')
    """
    return url_for("games_assets_bp.static", filename=f"cards/{code}.png")

def card_images(cards: List[int]) -> List[Dict[str, str]]:
    """
    Creates a small payload of {code,url} for the 4 cards.
    Suit choice is cosmetic; we randomize so the board looks “fresh”.
    """
    suits = random.choices(SUITS, k=len(cards))
    out: List[Dict[str, str]] = []
    for i, n in enumerate(cards):
        code = f"{rank_code(n)}{suits[i]}"
        out.append({"code": code, "url": card_image_url_from_assets(code)})
    return out


# ============================================================
# Minimal per-tab game state (shared baseline)
# ============================================================

def default_state() -> Dict[str, Any]:
    """
    A neutral, reusable default state for *any* math/puzzle game session.
    Individual blueprints can extend freely.
    """
    return {
        "stats": {
            # session totals
            "played": 0,
            "solved": 0,
            "revealed": 0,
            "skipped": 0,
            "total_time": 0,          # seconds

            # action-level
            "answer_attempts": 0,
            "answer_correct": 0,
            "answer_wrong": 0,
            "deal_swaps": 0,

            # optional per-level tallies (used by some summaries)
            "by_level": {},  # level -> {played, solved}
        },

        # sequencing / memory
        "recent_keys": [],
        "current_case_id": None,

        # timers
        "current_started_at": None,     # per-hand stopwatch start (float epoch)
        "competition_ends_at": None,    # optional competition end epoch (sec)

        # flow flags
        "counted_this_puzzle": False,   # first-interaction gate
        "hand_interacted": False,       # alias used by some routes

        # pool state (see _pool(state))
        # "pool": {...}

        # mode flags
        "help_disabled": False,
        "current_effective_level": None,
    }

def stats_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    s = state.get("stats", {})
    return {
        "played": s.get("played", 0),
        "solved": s.get("solved", 0),
        "revealed": s.get("revealed", 0),
        "skipped": s.get("skipped", 0),
        "total_time": s.get("total_time", 0),
        "answer_attempts": s.get("answer_attempts", 0),
        "answer_correct": s.get("answer_correct", 0),
        "answer_wrong": s.get("answer_wrong", 0),
        "deal_swaps": s.get("deal_swaps", 0),
    }

def ensure_played_once2(state: Dict[str, Any]) -> None:
    """
    Backward-compat version of bump_played_once; increments played on first interaction only.
    """
    if not state.get("counted_this_puzzle"):
        state.setdefault("stats", {}).setdefault("played", 0)
        state["stats"]["played"] += 1
        state["counted_this_puzzle"] = True
        state["hand_interacted"] = True

def ensure_played_once(state: Dict[str, Any]) -> None:
    """
    Backward-compat version of bump_played_once; increments played on first interaction only.
    """
    if not state.get("counted_this_puzzle"):
        st = state.setdefault("stats", {})
        st["played"] = int(st.get("played", 0)) + 1  # Preserve existing stats
        state["counted_this_puzzle"] = True
        state["hand_interacted"] = True

def start_timer(state: Dict[str, Any]) -> None:
    state["current_started_at"] = time.time()

def add_elapsed(state: Dict[str, Any]) -> None:
    ts = state.get("current_started_at")
    if ts:
        state.setdefault("stats", {}).setdefault("total_time", 0)
        state["stats"]["total_time"] += int(round(time.time() - ts))
    state["current_started_at"] = None


# ============================================================
# Expression complexity heuristic (for bucketing/analysis)
# ============================================================

def score_expression_complexity(expr: str) -> int:
    """
    Very lightweight heuristic:
      +,- = 1; *,/ = 2; ^ = 4; parentheses ignored.
    """
    s = (expr or "").replace(" ", "")
    score = 0
    for ch in s:
        if ch in "+-": score += 1
        elif ch in "*/": score += 2
        elif ch == "^": score += 4
    return score

# ============================================================
# Session & identity helpers
# ============================================================
def get_or_create_session_id(req) -> str:
    """
    Stable per-user (and optionally per-tab) session key:
      cookie 'session_id' (if present) else a new uuid4,
      optionally suffixed with ':<client_id>' (arg/body/header) to isolate tabs.
    """
    base = req.cookies.get("session_id") or str(uuid.uuid4())

    client = None
    try:
        client = req.args.get("client_id")
    except Exception:
        client = None
    if not client and getattr(req, "is_json", False):
        j = req.get_json(silent=True) or {}
        client = j.get("client_id")
    if not client:
        client = req.headers.get("X-Client-Session")

    if client:
        return f"{base}:{str(client)[:64]}"
    return base

def get_guest_id(req) -> Optional[str]:
    gid = None
    try:
        gid = req.args.get("guest_id")
    except Exception:
        pass
    if not gid and getattr(req, "is_json", False):
        j = req.get_json(silent=True) or {}
        gid = j.get("guest_id")
    if not gid:
        gid = req.headers.get("X-Guest-Id")
    return str(gid)[:64] if gid else None


def get_state(session_id: str) -> Dict[str, Any]:
    """Get session state by session ID"""
    return SESSIONS.setdefault(session_id, default_state())

def get_current_state(req) -> Dict[str, Any]:
    """Get current session state from request"""
    sid = get_or_create_session_id(req)
    return SESSIONS.setdefault(sid, default_state())

def comprehensive_stats_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive stats payload including all counters.
    This replaces the simpler stats_payload for full compatibility.
    """
    st = state.get("stats", {})
    return {
        "played": int(st.get("played", 0)),
        "solved": int(st.get("solved", 0)),
        "revealed": int(st.get("revealed", 0)),
        "skipped": int(st.get("skipped", 0)),
        "help_single": int(st.get("help_single", 0)),
        "help_all": int(st.get("help_all", 0)),
        "answer_attempts": int(st.get("answer_attempts", 0)),
        "answer_correct": int(st.get("answer_correct", 0)),
        "answer_wrong": int(st.get("answer_wrong", 0)),
        "deal_swaps": int(st.get("deal_swaps", 0)),
        "by_level": st.get("by_level", {}),
    }

# Also add these to the __all__ exports at the bottom:
__all__ = [
    # ... existing exports ...
    "get_state",
    "get_current_state", 
    "comprehensive_stats_payload",
]
# ============================================================
# Shared in-memory session store (per server process)
# ============================================================

SESSIONS: Dict[str, Dict[str, Any]] = {}
"""
key: session_id (cookie + optional client_id) -> per-session dict (see default_state()).
Persist to DB on /api/exit if desired. For now in-memory is sufficient.
"""


# ============================================================
# Competition helpers
# ============================================================

def competition_time_left(state: Dict[str, Any]) -> Optional[int]:
    """
    Returns seconds remaining for competition, or None if not running.
    Recognizes 'competition_ends_at' and legacy 'comp_ends_at'.
    """
    end = state.get("competition_ends_at") or state.get("comp_ends_at")
    if not end:
        return None
    left = int(round(end - time.time()))
    return max(0, left)


# ============================================================
# Pool helpers (custom/competition)
# ============================================================

def _pool(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures a pool structure exists on this session state.
    Structure:
      {
        'mode': 'custom'|'competition'|None,
        'ids':   [case_id, ...],
        'index': 0,      # next index to serve
        'status': { str(cid): {'status': 'unseen'|'shown'|'attempted'|'revealed'|'skipped'|'good',
                               'attempts': int } },
        'score':  { str(cid): 0|1 },   # 1 when solved correctly
        'done':   False,
      }
    """
    return state.setdefault("pool", {
        "mode": None,
        "ids": [],
        "index": 0,
        "status": {},
        "score": {},
        "done": False,
    })

def _mark_case_status(state: Dict[str, Any], case_id: int, action: str) -> None:
    p = _pool(state)
    key = str(case_id)
    entry = p["status"].setdefault(key, {"status": "unseen", "attempts": 0})

    if action == "shown":
        if entry["status"] == "unseen":
            entry["status"] = "shown"
    elif action == "attempt":
        entry["attempts"] += 1
        if entry["status"] in ("unseen", "shown"):
            entry["status"] = "attempted"
    elif action == "revealed":
        if entry["status"] != "good":
            entry["status"] = "revealed"
    elif action == "skipped":
        if entry["status"] != "good":
            entry["status"] = "skipped"
    elif action == "good":
        entry["status"] = "good"

def _set_case_solved(state: Dict[str, Any], case_id: int) -> None:
    p = _pool(state)
    p["score"][str(case_id)] = 1

def _pool_report(state: Dict[str, Any], lookup_level=None) -> List[Dict[str, Any]]:
    """
    Detailed list of pool items and status. If you pass lookup_level(case_id)->level,
    'level' will be included per row.
    """
    rows: List[Dict[str, Any]] = []
    p = _pool(state)
    for cid in p["ids"]:
        level = lookup_level(cid) if callable(lookup_level) else None
        e = p["status"].get(str(cid), {"status": "unseen", "attempts": 0})
        rows.append({"case_id": cid, "level": level, "status": e["status"], "attempts": e["attempts"]})
    return rows

def _pool_score(state: Dict[str, Any]) -> Tuple[Dict[str, int], List[int]]:
    """
    Returns (score_map, unfinished_ids). score_map: str(case_id) -> 0|1
    """
    p = _pool(state)
    score = {str(cid): int(p["score"].get(str(cid), 0)) for cid in p["ids"]}
    unfinished = [int(cid) for cid, v in score.items() if v == 0]
    return score, unfinished


# ============================================================
# Stats bumpers (reusable across games)
# ============================================================

def bump_played_once(state: Dict[str, Any], level_for_stats: Optional[str] = None) -> None:
    """Call on FIRST interaction (check/help/skip) of a hand."""
    if not state.get("counted_this_puzzle"):
        st = state.setdefault("stats", {})
        st["played"] = int(st.get("played", 0)) + 1
        state["counted_this_puzzle"] = True
        state["hand_interacted"] = True

        if level_for_stats:
            by = st.setdefault("by_level", {})
            row = by.setdefault(level_for_stats, {"played": 0, "solved": 0})
            row["played"] += 1

def bump_solved(state: Dict[str, Any], level_for_stats: Optional[str] = None) -> None:
    st = state.setdefault("stats", {})
    st["solved"] = int(st.get("solved", 0)) + 1
    if level_for_stats:
        by = st.setdefault("by_level", {})
        row = by.setdefault(level_for_stats, {"played": 0, "solved": 0})
        row["solved"] += 1

def bump_revealed(state: Dict[str, Any]) -> None:
    st = state.setdefault("stats", {})
    st["revealed"] = int(st.get("revealed", 0)) + 1

def bump_skipped(state: Dict[str, Any]) -> None:
    st = state.setdefault("stats", {})
    st["skipped"] = int(st.get("skipped", 0)) + 1

def bump_help(state: Dict[str, Any], all: bool = False) -> None:
    st = state.setdefault("stats", {})
    if all:
        st["help_all"] = int(st.get("help_all", 0)) + 1
    else:
        st["help_single"] = int(st.get("help_single", 0)) + 1

def bump_attempt(state: Dict[str, Any], correct: bool) -> None:
    st = state.setdefault("stats", {})
    st["answer_attempts"] = int(st.get("answer_attempts", 0)) + 1
    if correct:
        st["answer_correct"] = int(st.get("answer_correct", 0)) + 1
    else:
        st["answer_wrong"] = int(st.get("answer_wrong", 0)) + 1

def bump_deal_swap(state: Dict[str, Any]) -> None:
    st = state.setdefault("stats", {})
    st["deal_swaps"] = int(st.get("deal_swaps", 0)) + 1


# ===============================================================
# helper for insert play data to game_sessions, game_session_plays
# ===============================================================
# ---- tiny utils ----
def now_ms() -> int:
    return int(time.time() * 1000)

def compute_session_window(per: List[Dict], fallback_now: Optional[int] = None) -> Tuple[int, int]:
    if fallback_now is None:
        fallback_now = now_ms()
    started = min((r.get("started_at_ms") for r in per if r.get("started_at_ms")), default=fallback_now)
    ended   = max((r.get("ended_at_ms") for r in per if r.get("ended_at_ms")),   default=fallback_now)
    if ended < started: ended = started
    return int(started), int(ended)

# ---- human-friendly codes (two flavors) ----
def public_code_for(game_slug: str, sid: str | None, client_id: str | None,
                    digest_bytes: int = 6) -> str:
    """Random/hashed, non-guessable code (with entropy)."""
    salt = secrets.token_hex(4)
    key = f"{sid or ''}|{client_id or ''}|{time.time_ns()}|{salt}"
    h = hashlib.blake2s(key.encode(), digest_size=digest_bytes).digest()
    code = base64.b32encode(h).decode("ascii").rstrip("=")
    prefix = (game_slug or "GAM")[:3].upper()
    return f"{prefix}-{code[:4]}-{code[4:8]}"

def public_code_from_id(game_slug: str, session_id: int) -> str:
    """Deterministic code derived from the PK (simple, unique)."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
    n, s = session_id, ""
    while n: n, r = divmod(n, 32); s = alphabet[r] + s
    s = (s or "0").zfill(6)
    prefix = (game_slug or "GAM")[:3].upper()
    return f"{prefix}-{s[:3]}-{s[3:]}"

# ---- outcome normalization ----
PLAY_OUTCOMES = {
    "solved","skipped","incorrect","unsolved_exit","revealed_no_attempt","revealed_after_attempts"
}
def normalize_outcome(outcome: str | None, solved: bool, skipped: bool, attempts: int, helped: bool) -> str:
    s = (outcome or "").strip().lower()
    if s in ("solved_with_help","solve_with_help","solved-help"): s = "solved"
    if s in ("reveal","revealed"):
        s = "revealed_after_attempts" if attempts > 0 else "revealed_no_attempt"
    if s in PLAY_OUTCOMES: return s
    if solved: return "solved"
    if skipped: return "skipped"
    if attempts and not solved: return "incorrect"
    return "unsolved_exit"

# ---- state → plays rows ----
def plays_from_state(state: Dict, game_id: int) -> List[Dict]:
    per = state.get("per_puzzle") or []
    mode = (state.get("pool") or {}).get("mode")
    rows: List[Dict] = []
    for i, r in enumerate(per, start=1):
        solved   = bool(r.get("solved"))
        skipped  = bool(r.get("skipped"))
        attempts = int(r.get("attempts", 0))
        helped   = bool(r.get("helped"))
        outcome  = normalize_outcome(r.get("final_outcome"), solved, skipped, attempts, helped)
        rows.append(dict(
            session_id=None, game_id=game_id, play_seq=i,
            puzzle_id=r.get("case_id"), difficulty=r.get("level"), mode=mode,
            base=None, step=None, steps=None, suit=None,
            answer_final=r.get("final_answer"),
            correct=solved, help_used=helped, final_outcome=outcome,
        ))
    return rows

# ---- finalize current hand (if any) ----
def finalize_open_hand(state: Dict, *, default_outcome: str = "unsolved_exit", finalize_cb=None) -> bool:
    cur = (state or {}).get("current_hand")
    if not cur or cur.get("final_outcome"): return False
    if finalize_cb:
        finalize_cb(state, outcome=default_outcome)
    else:
        cur["final_outcome"] = default_outcome
        cur["ended_at_ms"] = now_ms()
        state.setdefault("per_puzzle", []).append(cur.copy())
        state["current_hand"] = None
    return True

# ---- reset runtime ----
def reset_runtime_state(state: Dict, *, preserve_identity: bool = True) -> None:
    ident = {}
    if preserve_identity:
        for k in ("client_id","guest_id","sid","session_sid"):
            if k in state: ident[k] = state[k]
    state.clear()
    state.update({
        "stats": {"played":0,"solved":0,"revealed":0,"skipped":0,"total_time":0,
                  "answer_attempts":0,"answer_correct":0,"answer_wrong":0,"deal_swaps":0,
                  "by_level":{},"help_all":0},
        "per_puzzle":[], "current_hand":None, "recent_keys":[],
        "pool":{"mode":None,"ids":[],"index":0,"done":False},
        **ident,
    })

# ---- persist (two patterns) ----

def persist_session_random(*, db, game_id: int, game_slug: str, state: dict, summary: dict) -> int:
    per   = state.get("per_puzzle") or []
    stats = state.get("stats") or {}

    # try to get a real sid, else a random token
    from flask import request
    sid_cookie = state.get("sid") or state.get("session_sid") or request.cookies.get("session_id") or secrets.token_hex(8)
    client_id  = state.get("client_id")
    guest_id   = state.get("guest_id")

    started_ms, ended_ms = compute_session_window(per, fallback_now=now_ms())

    stmt = text("""
        INSERT INTO app.game_sessions
          (game_id, session_sid, client_id, guest_id, public_code, player_name,
           started_at_ms, ended_at_ms,
           played, solved, skipped, incorrect, help_all, summary_json)
        VALUES
          (:game_id, :session_sid, :client_id, :guest_id, :public_code, :player_name,
           :started_at_ms, :ended_at_ms,
           :played, :solved, :skipped, :incorrect, :help_all, :summary_json)
        RETURNING id
    """).bindparams(bindparam("summary_json", type_=JSONB))

    base = dict(
        game_id=game_id,
        session_sid=sid_cookie,
        client_id=client_id,
        guest_id=guest_id,
        player_name=state.get("player_name"),
        started_at_ms=int(started_ms),
        ended_at_ms=int(ended_ms),
        played=int(stats.get("played", 0)),
        solved=int(stats.get("solved", 0)),
        skipped=int(stats.get("skipped", 0)),
        incorrect=int(stats.get("answer_wrong", 0)),
        help_all=int(stats.get("help_all", 0)),
        summary_json=summary,
    )

    sess_id = None
    for _ in range(6):  # regenerate on rare UNIQUE hits
        try:
            params = {**base, "public_code": public_code_for(game_slug, sid_cookie, client_id)}
            sess_id = db.session.execute(stmt, params).scalar_one()
            db.session.commit()
            break
        except IntegrityError as e:
            db.session.rollback()
            if "public_code" in str(e.orig):
                continue
            raise

    if sess_id is None:
        raise RuntimeError("Could not generate unique public_code")

    _persist_plays(db, state, game_id, sess_id)
    return sess_id

def persist_session_from_id(*, db, game_id: int, game_slug: str, state: Dict, summary: Dict) -> int:
    """Insert session first, then set deterministic public_code derived from PK (always unique)."""
    per = state.get("per_puzzle") or []
    stats = state.get("stats") or {}
    from flask import request
    sid_cookie = state.get("sid") or state.get("session_sid") or request.cookies.get("session_id")
    client_id  = state.get("client_id")
    guest_id   = state.get("guest_id")
    started_ms, ended_ms = compute_session_window(per, fallback_now=now_ms())
    ins = text("""
        INSERT INTO app.game_sessions
          (game_id, session_sid, client_id, guest_id, public_code, player_name,
           started_at_ms, ended_at_ms,
           played, solved, skipped, incorrect, help_all, summary_json)
        VALUES
          (:game_id, :session_sid, :client_id, :guest_id, 'PENDING', :player_name,
           :started_at_ms, :ended_at_ms,
           :played, :solved, :skipped, :incorrect, :help_all, :summary_json)
        RETURNING id
    """).bindparams(bindparam("summary_json", type_=JSONB))
    sess_id = db.session.execute(ins, dict(
        game_id=game_id, session_sid=sid_cookie, client_id=client_id, guest_id=guest_id,
        player_name=state.get("player_name"),
        started_at_ms=int(started_ms), ended_at_ms=int(ended_ms),
        played=int(stats.get("played",0)), solved=int(stats.get("solved",0)),
        skipped=int(stats.get("skipped",0)), incorrect=int(stats.get("answer_wrong",0)),
        help_all=int(stats.get("help_all",0)), summary_json=summary,
    )).scalar_one()
    code = public_code_from_id(game_slug, sess_id)
    db.session.execute(text("UPDATE app.game_sessions SET public_code=:c WHERE id=:id"),
                       {"c": code, "id": sess_id})
    db.session.commit()
    _persist_plays(db, state, game_id, sess_id)
    return sess_id

def _persist_plays(db, state: Dict, game_id: int, sess_id: int) -> None:
    plays = plays_from_state(state, game_id)
    if not plays: return
    for r in plays: r["session_id"] = sess_id
    db.session.execute(text("""
        INSERT INTO app.game_session_plays
          (session_id, game_id, play_seq, puzzle_id, difficulty, mode,
           base, step, steps, suit,
           answer_final, correct, help_used, final_outcome)
        VALUES
          (:session_id, :game_id, :play_seq, :puzzle_id, :difficulty, :mode,
           :base, :step, :steps, :suit,
           :answer_final, :correct, :help_used, :final_outcome)
    """), plays)
    db.session.commit()

# ============================================================
# game10 and 36 helpers
# ============================================================

_OPS = [
    ("+", lambda a,b: a+b),
    ("-", lambda a,b: a-b),
    ("*", lambda a,b: a*b),
    ("/", lambda a,b: a/b if b != 0 else None),
]

def solve_one(values, target):
    """Return one infix solution string or None."""
    nums = tuple(Fraction(x) for x in values)
    exps = tuple(str(int(x)) for x in values)
    return _search_one(nums, exps, Fraction(int(target)))

@lru_cache(maxsize=None)
def _search_one(nums, exps, target):
    n = len(nums)
    if n == 1:
        return exps[0] if nums[0] == target else None
    for i in range(n):
        for j in range(i+1, n):
            a,b = nums[i], nums[j]
            ea,eb = exps[i], exps[j]
            restn = [nums[k] for k in range(n) if k not in (i,j)]
            reste = [exps[k] for k in range(n) if k not in (i,j)]
            for sym,fn in _OPS:
                if sym in ("+","*") and a > b:
                    a1,b1,ea1,eb1 = b,a,eb,ea
                else:
                    a1,b1,ea1,eb1 = a,b,ea,eb
                try:
                    res = fn(a1,b1)
                except ZeroDivisionError:
                    res = None
                if res is None:
                    continue
                out = _search_one(tuple(restn+[res]), tuple(reste+[f"({ea1}{sym}{eb1})"]), target)
                if out: return out
    return None

def enumerate_solutions(values, target, limit=50):
    """Return up to `limit` unique infix solutions."""
    target = Fraction(int(target))
    sols, seen = [], set()
    def dfs(nums, exps):
        if len(sols) >= limit: return
        n = len(nums)
        if n == 1:
            if nums[0] == target:
                s = exps[0]
                if s not in seen:
                    seen.add(s); sols.append(s)
            return
        for i in range(n):
            for j in range(i+1, n):
                a,b = nums[i], nums[j]
                ea,eb = exps[i], exps[j]
                restn = [nums[k] for k in range(n) if k not in (i,j)]
                reste = [exps[k] for k in range(n) if k not in (i,j)]
                for sym,fn in _OPS:
                    if sym in ("+","*") and a > b:
                        a1,b1,ea1,eb1 = b,a,eb,ea
                    else:
                        a1,b1,ea1,eb1 = a,b,ea,eb
                    try:
                        res = fn(a1,b1)
                    except ZeroDivisionError:
                        res = None
                    if res is None:
                        continue
                    dfs(tuple(restn+[res]), tuple(reste+[f"({ea1}{sym}{eb1})"]))
                    if len(sols) >= limit: return
    dfs(tuple(Fraction(x) for x in values), tuple(str(int(x)) for x in values))
    return sols

# ============================================================
# Public exports
# ============================================================

__all__ = [
    # stores / identity
    "SESSIONS", "default_state", "stats_payload",
    "get_or_create_session_id", "get_guest_id",
    "get_state", "get_current_state", "comprehensive_stats_payload",

    # cards / assets
    "card_images", "card_image_url_from_assets", "rank_code",

    # values / expr helpers
    "values_key", "normalize_level", "normalize_rank_expr", "score_expression_complexity",

    # timers
    "start_timer", "add_elapsed", "competition_time_left",

    # pool helpers
    "_pool", "_mark_case_status", "_set_case_solved", "_pool_report", "_pool_score",

    # stats bumpers
    "ensure_played_once", "bump_played_once", "bump_solved", "bump_revealed",
    "bump_skipped", "bump_help", "bump_attempt", "bump_deal_swap",

    #others
    "finalize_open_hand", "persist_session", "reset_runtime_state",
]
