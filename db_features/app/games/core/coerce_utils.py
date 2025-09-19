# app/games/core/card_utils/coerce_utils.py
from typing import List, Optional, Dict, Any
import re

def values_key(values: List[int]) -> str:
    """Create a sorted key from values for consistent lookup."""
    return "-".join(map(str, sorted(values)))

def coerce_int_list(val) -> List[int]:
    """Coerce various input types to list of integers."""
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

def coerce_id_list(val) -> List[int]:
    """Coerce various input types to list of IDs."""
    return coerce_int_list(val)  # Same implementation for now

def normalize_level(level: Optional[str]) -> str:
    """Normalize difficulty level strings."""
    if level is None: return "easy"
    ALIASES = {'0':'easy','easy':'easy','1':'medium','medium':'medium',
               '2':'hard','3':'hard','hard':'hard','4':'challenge',
               'challenge':'challenge','nosol':'nosol'}
    return ALIASES.get(str(level).lower(), str(level).lower())
