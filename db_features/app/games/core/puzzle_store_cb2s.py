# app/games/core/puzzle_store_cb2s.py
from __future__ import annotations
import random, time, os
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy import text
from app.db import db

DEFAULT_CAP = int(os.getenv("CB2S_CAP", "100"))

@dataclass(frozen=True)
class CB2SPuzzle:
    id: int
    external_id: str
    difficulty: str
    cards: List[int]  # [base, 2, 2, 2]

_store: Dict[str, Any] | None = None

def init_store(force: bool = False, cap: Optional[int] = None) -> None:
    """Load up-to 'cap' puzzles per difficulty into memory. Also builds an 'all' pool."""
    global _store
    if _store is not None and not force:
        return

    cap = cap or DEFAULT_CAP
    rows = db.session.execute(text("""
        SELECT id, external_id, difficulty, content_json
        FROM app.count_by_puzzles
        WHERE is_active = TRUE
    """)).mappings().all()

    by_level: Dict[str, List[CB2SPuzzle]] = {"easy": [], "medium": [], "hard": []}

    for r in rows:
        cj = r["content_json"] or {}
        cards = cj.get("cards") or []
        if not isinstance(cards, list) or len(cards) != 4:
            continue
        p = CB2SPuzzle(
            id=int(r["id"]),
            external_id=r["external_id"],
            difficulty=(r["difficulty"] or "easy").lower(),
            cards=[int(x) for x in cards],
        )
        lvl = p.difficulty if p.difficulty in by_level else "easy"
        by_level[lvl].append(p)

    for lvl in ("easy", "medium", "hard"):
        random.shuffle(by_level[lvl])
        if cap and len(by_level[lvl]) > cap:
            by_level[lvl] = by_level[lvl][:cap]

    all_pool: List[CB2SPuzzle] = by_level["easy"] + by_level["medium"] + by_level["hard"]
    random.shuffle(all_pool)
    if cap and len(all_pool) > cap:
        all_pool = all_pool[:cap]

    _store = {"by_level": by_level, "all": all_pool, "loaded_at": time.time(), "cap": cap}

def _ensure_loaded(cap: Optional[int] = None) -> None:
    if _store is None:
        init_store(force=False, cap=cap)

def pool_report() -> Dict[str, int]:
    _ensure_loaded()
    return {
        "easy": len(_store["by_level"]["easy"]),
        "medium": len(_store["by_level"]["medium"]),
        "hard": len(_store["by_level"]["hard"]),
        "all": len(_store["all"]),
        "cap": _store["cap"],
    }

def random_next(level: str, avoid_ids: Optional[set[int]] = None) -> Tuple[Optional[CB2SPuzzle], bool]:
    """Random puzzle for level (easy|medium|hard|all); avoids IDs; indicates pool exhaustion."""
    _ensure_loaded()
    lvl = level.lower()
    pool: List[CB2SPuzzle]
    if lvl in ("easy", "medium", "hard"):
        pool = _store["by_level"][lvl]
    else:
        pool = _store["all"]

    avoid = avoid_ids or set()
    candidates = [p for p in pool if p.id not in avoid]
    pool_done = False
    if not candidates:
        candidates = pool[:]
        pool_done = True

    if not candidates:
        return None, pool_done
    return random.choice(candidates), pool_done

def expected_final(cards: List[int]) -> int:
    """For [base,2,2,2], final is base + 2 + 2 + 2."""
    if not cards or not isinstance(cards, list) or len(cards) != 4:
        return 0
    return int(cards[0]) + int(cards[1]) + int(cards[2]) + int(cards[3])

