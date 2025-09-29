# app/home/routes.py
from flask import Blueprint, render_template, url_for

bp = Blueprint("home", __name__)

@bp.get("/")
def index():
    # Minimal game list (kept as-is)
    games = [
        type("Obj",(object,),{"key":"game24","name":"24-Point (Classic)"})(),
        type("Obj",(object,),{"key":"count_by_2s","name":"Count by 2s"})(),
        {"key": "sum4",   "name": "Sum 4 Cards"},
    ]

    # NEW: quick target links (build hrefs here so Jinja stays simple)
    quick_links = [
        {"label": "Play 24-Point", "href": url_for("game24.play", target=24)},
        {"label": "Play 10-Point", "href": url_for("game24.play", target=10)},
        {"label": "Play 36-Point", "href": url_for("game24.play", target=36)},
        {"label": "Custom target…", "href": url_for("game24.play", target="custom")},
    ]

    # DEBUG: Check if sum4.play endpoint exists
    from flask import current_app
    with current_app.app_context():
        try:
            sum4_url = url_for('sum4.play')
            print(f"✅ sum4.play URL: {sum4_url}")
        except Exception as e:
            print(f"❌ sum4.play error: {e}")

        # List all sum4 endpoints
        sum4_endpoints = [rule.endpoint for rule in current_app.url_map.iter_rules() if rule.endpoint.startswith('sum4.')]
        print(f"sum4 endpoints: {sum4_endpoints}")

    return render_template("home/index.html", games=games, quick_links=quick_links)

