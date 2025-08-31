# web/app.py - UPDATED FOR YOUR STRUCTURE
#export FLASK_APP=app.py
#export FLASK_ENV=development 
import os
import sys
from flask import Flask
from logging.handlers import RotatingFileHandler
import logging

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_app(config_class='web.config.Config'):
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Initialize extensions
    init_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Setup logging
    setup_logging(app)
    
    return app

def init_extensions(app):
    """Initialize all extensions"""
    from lib.database import db
    db.init_app(app)
    
    # Initialize authentication if needed
    from lib.auth import init_auth
    init_auth(app)

def register_blueprints(app):
    """Register all blueprints from the blueprints directory"""
    # Main routes
    from blueprints.core import core_bp
    from blueprints.auth import auth_bp
    from blueprints.leaderboard import leaderboard_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(leaderboard_bp, url_prefix='/leaderboard')
    
    # API routes (all games) - FIXED THIS LINE
    from blueprints.api.game24 import game24_bp
    app.register_blueprint(game24_bp, url_prefix='/api/game24')
    from blueprints.api.math_puzzle import math_puzzle_bp
    app.register_blueprint(math_puzzle_bp, url_prefix='/api/math_puzzle')


def setup_logging(app):
    """Setup application logging"""
    if not app.debug:
        log_dir = os.path.join(app.root_path, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'wearelittleteachers.log'),
            maxBytes=10240,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('WeAreLittleTeachers startup')

# For flask run command
app = create_app()
