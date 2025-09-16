from app import create_app
from app.db import db
from app.models import Game, GameItem, User, Organization, Classroom, Enrollment, Event, Puzzle
app = create_app()
with app.app_context():
    print("GameItem.query.count=",GameItem.query.count())
    print("Game.query.count=",Game.query.count())
    print("User.query.count=",User.query.count())
    print("Organization.query.count=",Organization.query.count())
    print("Classroom.query.count=",Classroom.query.count())
    print("Enrollment.query.count=",Enrollment.query.count())
    print("Event.query.count=",Event.query.count())
    print("game24_puzzle.query.count=",Puzzle.query.count())

