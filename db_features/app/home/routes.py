from flask import Blueprint, render_template

bp = Blueprint("home", __name__)

@bp.get("/")
def index():
    # Minimal “game list”—you can wire this to DB later
    games = [type("Obj",(object,),{"key":"game24","name":"24-Point (Classic)"})()]
    return render_template("home/index.html", games=games)
