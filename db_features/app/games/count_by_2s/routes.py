from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify, make_response, url_for, current_app, redirect
from flask_login import login_required, current_user
from uuid import uuid4
from sqlalchemy import text
from datetime import datetime, timezone
from ...db import db
from ...models import Game, GameSession   # GameSession maps to sessions table
import logging, random
#from app.models import Game, GameSession

bp = Blueprint(
    "count_by_2s",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static"
)

log = logging.getLogger(__name__)

# --- helpers --------------------------------------------------------
ENABLE_ALL_DIFFICULTY = True  # ← flip to False to hide/disable "all"

def _is_all(level: str | None) -> bool:
    return (level or "").lower() == "all"

def _get_session_from_cookie():
    sid = request.cookies.get("db_session_id")
    if not sid:
        return None
    try:
        return GameSession.query.get(int(sid))
    except Exception:
        return None

def _get_seen(sess, key: str) -> set[int]:
    if not sess or sess.meta is None:
        return set()
    val = sess.meta.get(key)
    if isinstance(val, list):
        try:
            return set(int(x) for x in val)
        except Exception:
            return set()
    return set()

def _set_seen(sess, key: str, seen_ids: set[int]):
    if not sess:
        return
    if sess.meta is None:
        sess.meta = {}
    sess.meta[key] = sorted(int(x) for x in (seen_ids or set()))
    db.session.add(sess)
    db.session.commit()

def _rank_code(n:int)->str:
    n = int(n)
    return {1:'A',10:'T',11:'J',12:'Q',13:'K'}.get(n, str(n))


def _cards_to_images(cards: list[int],
                     randomize_twos: bool = True,
                     randomize_base: bool = False) -> list[dict]:
    """
    Build image URLs using shared assets:
      /games/assets/cards/<Rank><Suit>.png

    - Base card (index 0):
        * by default NOT randomized (keeps behavior stable).
        * set randomize_base=True if you want it randomized too.
    - The following three "2" cards:
        * randomized by default (randomize_twos=True).
        * avoids immediate suit repeats for nicer variety.
    """
    suits = ['C', 'D', 'H', 'S']
    out: list[dict] = []
    prev_s = None

    for i, n in enumerate(cards[:4]):
        if i == 0:
            # base card suit: fixed (first suit) or randomized if you want
            s = random.choice(suits) if randomize_base else suits[0]
        else:
            if randomize_twos:
                # pick a suit, avoid repeating the immediately previous suit
                choices = suits[:]
                if prev_s in choices and len(choices) > 1:
                    choices.remove(prev_s)
                s = random.choice(choices)
            else:
                # fallback: positional cycle
                s = suits[i % 4]
        prev_s = s

        code = f"{_rank_code(int(n))}{s}"
        url  = url_for("games_assets_bp.static", filename=f"cards/{code}.png")
        out.append({"code": code, "url": url})

    return out


def _get_game_and_store():
    """Return (game, table_name) for slug 'count-by-2s' reading game_profiles.data_store_table."""
    game = Game.query.filter_by(slug="count-by-2s").first()
    if not game:
        # seed if missing (you already inserted this, but safe)
        game = Game(slug="count-by-2s", title="Count by 2s", subject="math", modality="cards", is_active=True)
        db.session.add(game); db.session.flush()

    row = db.session.execute(text("""
        SELECT data_store_table
        FROM app.game_profiles
        WHERE game_id = :gid
        LIMIT 1
    """), {"gid": game.game_id}).mappings().first()

    table = (row["data_store_table"] if row else "app.count_by_puzzles")
    # guard: only allow app.<name>
    if not isinstance(table, str) or not table.startswith("app."):
        table = "app.count_by_puzzles"
    return game, table

def _random_row_from_store(table: str, game_id: int, level: str | None, avoid_ids: list[int] | None = None):
    where = "WHERE game_id = :gid AND is_active"
    params = {"gid": game_id}

    lvl = (level or "").lower()
    if lvl in ("easy", "medium", "hard", "challenge") and not _is_all(lvl):
        where += " AND difficulty = :lvl"
        params["lvl"] = lvl  # safe: enumerated above

    if avoid_ids:
        ids = ",".join(str(int(x)) for x in avoid_ids)
        where += f" AND id NOT IN ({ids})"

    sql = f"""
      SELECT id, content_json, solution_json, difficulty
      FROM {table}
      {where}
      ORDER BY random() LIMIT 1
    """
    return db.session.execute(text(sql), params).mappings().first()


def _expected_final(cards:list[int]) -> int:
    """
    Our format is [base, 2, 2, 2] (A..K then three 2s).
    Final = base + 2 + 2 + 2
    """
    if not cards: return 0
    base = int(cards[0])
    return base + 6

def _pool_size(table:str, game_id:int, level:str|None) -> int:
    where = "WHERE game_id = :gid AND is_active"
    params = {"gid": game_id}
    if level in ("easy","medium","hard","challenge"):
        where += " AND difficulty = :lvl"
        params["lvl"] = level
    sql = f"SELECT COUNT(*) AS n FROM {table} {where}"
    return int(db.session.execute(text(sql), params).scalar() or 0)

# --- pages ----------------------------------------------------------

@bp.get("/")
def index():
    return redirect(url_for("count_by_2s.play"))

@bp.get("/play")
@login_required
def play():
    level = (request.args.get("level") or "").strip().lower() or None

    if not level:
        level = "all" if ENABLE_ALL_DIFFICULTY else "easy"

    # if someone passes ?level=all but the feature is off, fall back safely
    if level == "all" and not ENABLE_ALL_DIFFICULTY:
        level = "easy"

    game, table = _get_game_and_store()

    # Start a DB session row for attempts
    sess = GameSession(session_uuid=uuid4(), user_id=current_user.id, game_id=game.game_id)
    db.session.add(sess); db.session.commit()

    # Pre-pick one puzzle so the first "Deal" is instant
    row = _random_row_from_store(table, game.game_id, level)
    # If the store is empty, synthesize a trivial one: base 1
    if not row:
        cards = [1, 2, 2, 2]
        payload = {
            "seq": 0,
            "case_id": 1,
            "question": cards,
            "values": cards,
            "images": _cards_to_images(cards, randomize_twos=True, randomize_base=True),
            "difficulty": (row["difficulty"] if row else (level or "easy")),
            "help_disabled": False,
            "pool_done": False,
        }
    else:
        cards = list(map(int, (row["content_json"].get("cards") or [])))[:4]
        if not cards: cards = [1,2,2,2]
        payload = {
            "seq": 0,
            "case_id": int(row["content_json"].get("case_id", row["id"])),
            "question": cards,
            "values": cards,
            "images": _cards_to_images(cards, randomize_twos=True, randomize_base=True),
            "help_disabled": False,
            "pool_done": False,
        }

    api_base = url_for("count_by_2s.api_next").rsplit("/", 1)[0]  # "/count_by_2s/api"

    resp = make_response(render_template(
        "cb2s_play.html",
        title=game.title,                 # use DB title
        session_id=sess.id,
        first_payload=payload,            # so UI can render immediately
        cb2_api_base=api_base,            # override JS default
        enable_all_mode=ENABLE_ALL_DIFFICULTY,
        default_level=level,
    ))
    resp.set_cookie("db_session_id", str(sess.id), max_age=3600, httponly=True, samesite="Lax", path="/")
    return resp

# --- API (minimal, Game24-compatible shell) ------------------------

@bp.get("/api/next")
def api_next():
    level = (request.args.get("level") or "").strip().lower() or None
    game, table = _get_game_and_store()
    sess = _get_session_from_cookie()

    seen_key = f"seen_{level or 'any'}"
    seen = _get_seen(sess, seen_key) if sess else set()

    # get a new row avoiding seen ids
    row = _random_row_from_store(table, game.game_id, level, sorted(seen))
    pool_done = False
    pool_exhausted = False
    if not row:
        _set_seen(sess, seen_key, set())
        row = _random_row_from_store(table, game.game_id, level, [])
        pool_exhausted = True

    announce_levels = {"custom", "competition"}
    pool_done = pool_exhausted and (level in announce_levels)

    if not row:
        # exhausted: reset seen, try again
        if sess:
            _set_seen(sess, seen_key, set())
            db.session.commit()
        row = _random_row_from_store(table, game.game_id, level, [])
        pool_done = True

    if not row:
        cards = [random.randint(1,13), 2, 2, 2]
        case_id = 0
    else:
        cards = list(map(int, (row["content_json"].get("cards") or [])))[:4] or [1,2,2,2]
        case_id = int(row["content_json"].get("case_id", row["id"]))

        # mark seen
        if sess and case_id:
            seen.add(row["id"])  # track by actual id
            _set_seen(sess, seen_key, seen)
            db.session.commit()

    seq = int(request.args.get("seq", 0)) + 1
    data = {
        "ok": True,
        "seq": seq,
        "case_id": case_id,
        "question": cards,
        "values": cards,
        "images": _cards_to_images(cards, randomize_twos=True, randomize_base=True),
        "difficulty": row["difficulty"] if row else (level or None),
        "help_disabled": False,
        "pool_done": pool_done,
    }
    return jsonify(data), 200


@bp.post("/api/check")
def api_check():
    """
    Game24 client posts {"values":[...],"answer":"..."}.
    For Count-by-2s we accept a final number; correct if == base+6.
    """
    j = request.get_json(silent=True) or {}
    vals = j.get("values") or []
    ans  = (j.get("answer") or "").strip()
    try:
        cards = list(map(int, vals))[:4]
    except Exception:
        cards = []
    exp = _expected_final(cards)

    try:
        typed = int(ans)
    except Exception:
        return jsonify({"ok": False, "reason": "Enter the final number only."}), 200

    ok = (typed == exp)
    return jsonify({"ok": ok, "value": typed, "kind": "final-number"}), 200

@bp.post("/api/help")
def api_help():
    """
    Return a friendly sequence; we’ll compute if solution_json is missing.
    """
    j = request.get_json(silent=True) or {}
    vals = j.get("values") or []
    try:
        cards = list(map(int, vals))[:4]
    except Exception:
        cards = []

    if not cards:
        return jsonify({"has_solution": False, "solutions": []}), 200

    base = int(cards[0])
    seq  = [base+2, base+4, base+6]
    lines = [
        f"{_rank_code(base)} + 2 = {base+2}",
        f"{_rank_code(base)} + 2 + 2 = {base+4}",
        f"{_rank_code(base)} + 2 + 2 + 2 = {base+6}",
    ]
    return jsonify({"has_solution": True, "solutions": lines}), 200

@bp.get("/api/pool_report")
def api_pool_report():
    return jsonify({"ok": True, "stats": {"played":0,"solved":0,"revealed":0,"skipped":0}}), 200

@bp.post("/api/restart")
def api_restart():
    return jsonify({"ok": True}), 200

@bp.post("/api/exit")
def api_exit():
    j = request.get_json(silent=True) or {}
    stats = j.get("stats") or {}
    sess = _get_session_from_cookie()
    if sess:
        sess.ended_at = datetime.now(timezone.utc)
        if sess.meta is None:
            sess.meta = {}
        sess.meta["stats"] = stats
        db.session.add(sess)
        db.session.commit()
    return jsonify({"ok": True, "next_url": url_for("home.index")}), 200
