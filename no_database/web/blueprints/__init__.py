# web/blueprints/__init__.py
from .api.game24 import game24_bp
from .core import core_bp

def register_blueprints(app):
    """Register all blueprints with the Flask application"""
    app.register_blueprint(core_bp)
    app.register_blueprint(game24_bp, url_prefix='/api/game24')
    print("Blueprints registered successfully!")
