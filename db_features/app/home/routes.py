# app/home/routes.py
from flask import Blueprint, render_template, url_for

bp = Blueprint("home", __name__)

@bp.get("/")
def index():
    # Minimal game list (kept as-is)
    games = [
        type("Obj",(object,),{"key":"game24","name":"24-Point (Classic)"})(),
        type("Obj",(object,),{"key":"count_by_2s","name":"Count by 2s"})(),
    ]

    # NEW: quick target links (build hrefs here so Jinja stays simple)
    quick_links = [
        {"label": "Play 24-Point", "href": url_for("game24.play", target=24)},
        {"label": "Play 10-Point", "href": url_for("game24.play", target=10)},
        {"label": "Play 36-Point", "href": url_for("game24.play", target=36)},
        {"label": "Custom target…", "href": url_for("game24.play", target="custom")},
    ]

    return render_template("home/index.html", games=games, quick_links=quick_links)

