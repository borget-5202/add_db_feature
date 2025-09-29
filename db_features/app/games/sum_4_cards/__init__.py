# app/games/sum_4_cards/__init__.py
from flask import Blueprint

bp = Blueprint(
    "sum4",
    __name__,
    url_prefix="/games/sum_4_cards",
    template_folder="templates",
    static_folder="static",
)

