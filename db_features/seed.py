from uuid import uuid4
from pathlib import Path
import json
from app import create_app, db
from app.models import Game, Puzzle  # ensure these models exist & use schema="app"

def upsert_game(slug, title, modality, description=""):
    g = Game.query.filter_by(slug=slug).first()
    if not g:
        g = Game(slug=slug, title=title, modality=modality, description=description)
        db.session.add(g)
        db.session.commit()
        print(f"✅ Added game: {slug}")
    else:
        print(f"ℹ️ Game exists: {slug}")
    return g

def ensure_puzzle(game, external_id, title=None, difficulty=None, content_json=None, solution_json=None):
    p = Puzzle.query.filter_by(game_id=game.id, external_id=external_id).first()
    if p:
        return False
    p = Puzzle(
        game_id=game.id,
        external_id=external_id,
        title=title,
        difficulty=difficulty,
        content_json=content_json or {},
        solution_json=solution_json,
    )
    db.session.add(p)
    return True

def import_game24_from_answers(game, answers_path, limit=None):
    path = Path(answers_path)
    if not path.exists():
        print(f"⚠️ answers.json not found at: {path}")
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("⚠️ answers.json format not a list; adjust loader.")
        return 0

    inserted = 0
    for i, item in enumerate(data, start=1):
        if limit and inserted >= limit:
            break

        # Try to derive a stable external_id
        ext_id = str(item.get("case_id") or item.get("id") or i).zfill(4)

        # Difficulty if present; otherwise leave None
        diff = item.get("difficulty")
        # Store the raw record as content_json so we can evolve later
        ok = ensure_puzzle(
            game,
            external_id=ext_id,
            title=item.get("title"),
            difficulty=diff,
            content_json=item,
            solution_json=item.get("solutions") or item.get("solution"),
        )
        if ok:
            inserted += 1
            if inserted % 200 == 0:
                db.session.commit()
                print(f"   ... inserted {inserted} so far")

    db.session.commit()
    return inserted

def run():
    app = create_app()
    with app.app_context():
        # Seed games
        g24 = upsert_game(
            "game24", "24-Point Card Game", "cards",
            "Use arithmetic with 4 cards to make 24."
        )
        area = upsert_game(
            "area-builder", "Area Builder", "real_world",
            "Measure real objects and compute area."
        )

        # Seed at least one puzzle for each game (so UI has something immediately)
        added = 0
        added += ensure_puzzle(
            g24, "24-0001", title="A,5,7,K", difficulty="easy",
            content_json={"cards":[1,5,7,13], "ranks":["A","5","7","K"]},
            solution_json=None
        ) or 0
        added += ensure_puzzle(
            area, "AREA-0001", title="Measure your desk", difficulty="easy",
            content_json={"scenario":"Measure your table", "units":["cm","in"], "inputs":["length","width"]},
            solution_json={"formula":"length*width"}
        ) or 0
        if added:
            db.session.commit()
            print(f"✅ Added {added} starter puzzles")

        # OPTIONAL: Import your full Game24 set from answers.json
        # Adjust the path to where your file lives in your project:
        answers_path = "app/games/game24/static/answers.json"
        inserted = import_game24_from_answers(g24, answers_path, limit=None)  # set limit=100 to test
        if inserted:
            print(f"✅ Imported {inserted} Game24 puzzles from answers.json")

        # Summary
        games_count = Game.query.count()
        puzzles_count = Puzzle.query.count()
        print(f"\n📊 Summary")
        print(f"   Games:   {games_count}")
        print(f"   Puzzles: {puzzles_count}")

if __name__ == "__main__":
    run()

