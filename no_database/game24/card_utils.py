# card_utils.py
from typing import Dict, Any, List
import hashlib
import random

RANK_TO_VALUE = {
    "A": 1, "J": 11, "Q": 12, "K": 13,
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "7": 7, "8": 8, "9": 9, "10": 10,
    "a": 1, "j": 11, "q": 12, "k": 13,  # lowercase
}
VALUE_TO_RANK = {1: "A", 11: "J", 12: "Q", 13: "K"}

def rank_to_value(rank: str) -> int:
    r = str(rank).strip().strip('"').strip("'")
    if r in RANK_TO_VALUE:
        return RANK_TO_VALUE[r]
    if r.isdigit():
        return int(r)
    raise ValueError(f"Unrecognized rank: {rank}")

def value_to_rank(v: int) -> str:
    return VALUE_TO_RANK.get(int(v), str(int(v)))

def get_values(p: Dict[str, Any]) -> List[int]:
    """Prefer precomputed values; else derive from cards."""
    if "values" in p and p["values"]:
        return [int(x) for x in p["values"]]
    ranks = p.get("cards", []) or []
    return [rank_to_value(r) for r in ranks]

def get_ranks_for_display(p: Dict[str, Any]) -> List[str]:
    """Prefer rank strings; else map numeric values to ranks (11->J, etc.)."""
    ranks = p.get("cards")
    if isinstance(ranks, list) and len(ranks) == 4:
        out = []
        for x in ranks:
            sx = str(x)
            out.append(value_to_rank(int(sx)) if sx.isdigit() else sx)
        return out
    return [value_to_rank(v) for v in get_values(p)]

def _rng_for(values: List[int], salt: str = "") -> random.Random:
    seed_src = f"{tuple(values)}|{salt}"
    seed = int(hashlib.sha256(seed_src.encode()).hexdigest(), 16) % (10**8)
    return random.Random(seed)

__all__ = ["rank_to_value", "value_to_rank", "get_values", "get_ranks_for_display", "_rng_for"]

