# game24/card_assets.py
import random
import os, html
from typing import List, Dict, Any
import os
_warned_missing = set()

SUITS = ["S", "H", "D", "C"]  # Spades, Hearts, Diamonds, Clubs
VALUE_TO_RANK = {1:"A", 11:"J", 12:"Q", 13:"K"}

def value_to_rank(v: int) -> str:
    return VALUE_TO_RANK.get(int(v), str(int(v)))

def pick_card_images(
    values: List[int],
    theme: str = "classic",
    pictures_root: str = "pictures",
    allow_duplicate_suit: bool = True,
    rng: random.Random | None = None
) -> List[Dict[str, Any]]:
    """
    Given 4 numeric values (e.g., [4,4,3,4]), return a list of dicts:
      { "value": 4, "rank": "4", "suit": "H", "code": "4H", "path": "pictures/<theme>/4H.png" }

    - If allow_duplicate_suit=True, suits are sampled with replacement (simplest).
    - If False, will try to avoid reusing the same suit until it runs out.
    """
    r = rng or random
    result: List[Dict[str, Any]] = []
    pool = SUITS.copy()

    for v in values:
        rank = value_to_rank(v)
        if allow_duplicate_suit:
            suit = r.choice(SUITS)
        else:
            # try not to reuse suits; if exhausted, reset pool
            if not pool:
                pool = SUITS.copy()
            suit = r.choice(pool)
            pool.remove(suit)

        code = f"{rank}{suit}"
        path = f"{pictures_root}/{theme}/{code}.png"
        if not os.path.exists(path) and path not in _warned_missing:
            print(f"[warn] missing image: {path}")
            _warned_missing.add(path)
        result.append({"value": int(v), "rank": rank, "suit": suit, "code": code, "path": path})
    return result

# add at top with others

def render_question_html(images, title="24‑Point", outfile="question_preview.html"):
    """
    images: list of dicts from pick_card_images(...) with "path" keys
    writes a simple HTML file that shows the four cards side-by-side.
    """
    # file:// absolute paths so the browser can load local files
    cards_html = []
    for img in images:
        src = os.path.abspath(img["path"])
        cards_html.append(f'<img src="file://{src}" alt="{html.escape(img["code"])}" style="height:180px;margin:8px;">')

    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px; }}
    .wrap {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
    .label {{ margin-top: 12px; color:#444; }}
  </style>
</head>
<body>
  <h2>{html.escape(title)}</h2>
  <div class="wrap">
    {''.join(cards_html)}
  </div>
</body>
</html>"""
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return os.path.abspath(outfile)

