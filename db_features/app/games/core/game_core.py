# app/games/core/game_core.py
from __future__ import annotations
from typing import Dict, Any, List
import random, time
from flask import url_for
import re

# -------------------------------
# Values / difficulty helpers
# -------------------------------
def values_key(vals: List[int]) -> str:
    return "-".join(f"{int(x):02d}" for x in sorted(map(int, vals or [])))

def normalize_level(level: str) -> str:
    level = (level or "").strip().lower()
    # include 'all' for “any difficulty” pools
    return level if level in ("easy", "medium", "hard", "challenge", "nosol", "all") else "medium"


# -------------------------------
# Rank-letter → number normalization (A,T,J,Q,K)
# -------------------------------
_RANK_TO_NUM = {"A": "1", "T": "10", "J": "11", "Q": "12", "K": "13"}
_RANK_EXPR_RE = re.compile(r"\b([ATJQK])\b", re.IGNORECASE)

def normalize_rank_expr(expr: str) -> str:
    """
    Converts rank letters to their numeric equivalents in an arithmetic
    expression before parsing, e.g. 'K+K-J+9' -> '13+13-11+9'.
    Matches whole tokens only, so variables like 'AK' aren't replaced.
    """
    if not expr:
        return expr
    def repl(m: re.Match) -> str:
        return _RANK_TO_NUM[m.group(1).upper()]
    return _RANK_EXPR_RE.sub(repl, expr)

# -------------------------------
# Card/rank helpers + image URLs
# -------------------------------
_RANK = {1: "A", 10: "T", 11: "J", 12: "Q", 13: "K"}
SUITS = ("S", "H", "D", "C")

def rank_code(n: int) -> str:
    return _RANK.get(int(n), str(int(n)))

def card_image_url_from_assets(code: str) -> str:
    """
    Uses the shared assets blueprint. PNGs live at:
      app/games/assets/cards/<code>.png
    """
    return url_for("games_assets_bp.static", filename=f"cards/{code}.png")

def card_images(cards: List[int]) -> List[Dict[str, str]]:
    suits = random.choices(SUITS, k=len(cards))
    out = []
    for i, n in enumerate(cards):
        code = f"{rank_code(n)}{suits[i]}"
        out.append({"code": code, "url": card_image_url_from_assets(code)})
    return out

# -------------------------------
# Minimal per-tab game state
# -------------------------------
def default_state() -> Dict[str, Any]:
    return {
        "stats": {
            "played": 0, "solved": 0, "revealed": 0, "skipped": 0, "total_time": 0,
            "answer_attempts": 0, "answer_correct": 0, "answer_wrong": 0, "deal_swaps": 0,
        },
        "recent_keys": [],
        "current_case_id": None,
        "current_started_at": None,
        "counted_this_puzzle": False,
    }

def stats_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    s = state["stats"]
    return {
        "played": s["played"], "solved": s["solved"], "revealed": s["revealed"],
        "skipped": s["skipped"], "total_time": s["total_time"],
        "answer_attempts": s["answer_attempts"], "answer_correct": s["answer_correct"],
        "answer_wrong": s["answer_wrong"], "deal_swaps": s["deal_swaps"],
    }

def ensure_played_once(state: Dict[str, Any]) -> None:
    if not state.get("counted_this_puzzle"):
        state["stats"]["played"] += 1
        state["counted_this_puzzle"] = True

def start_timer(state: Dict[str, Any]) -> None:
    state["current_started_at"] = time.time()

def add_elapsed(state: Dict[str, Any]) -> None:
    ts = state.get("current_started_at")
    if ts:
        state["stats"]["total_time"] += int(round(time.time() - ts))
    state["current_started_at"] = None

# -------------------------------
# Expression complexity heuristic
# (used by Game24 store bucketing)
# -------------------------------
def score_expression_complexity(expr: str) -> int:
    """
    Very lightweight heuristic:
      +,- = 1; *,/ = 2; ^ = 4; parentheses ignored
    """
    s = (expr or "").replace(" ", "")
    score = 0
    for ch in s:
        if ch in "+-": score += 1
        elif ch in "*/": score += 2
        elif ch == "^": score += 4
    return score

