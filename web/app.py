from flask import Flask
from config import Config
from shared_state import init_shared_state
import os, logging
from logging.handlers import RotatingFileHandler

def create_app():
    app = Flask(__name__)

    # Configure logging
    if not app.debug:
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.mkdir('logs')

        # File handler - rotates logs when they get too big
        file_handler = RotatingFileHandler('logs/game24.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('Game24 startup')

    app.config.from_object(Config)
    
    # Initialize shared state
    init_shared_state()
    
    # Register blueprints
    from blueprints import register_blueprints
    register_blueprints(app)

    #with app.app_context():
    #    from blueprints.api.game24 import init_game24_data
    #    init_game24_data()
    
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
