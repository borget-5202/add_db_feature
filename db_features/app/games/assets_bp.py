# app/games/assets_bp.py
from flask import Blueprint
import os

assets_bp = Blueprint(
    "games_assets_bp",
    __name__,
    static_folder="assets",            # folder relative to this file's package
    static_url_path="/games/assets"    # URL prefix
)

