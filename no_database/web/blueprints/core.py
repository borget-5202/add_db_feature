#web/blueprints/core.py
from flask import Blueprint, jsonify, send_file
print("this is core under blueprint")

core_bp = Blueprint('core', __name__)

#@core_bp.route('/api/games')
#def list_games():
#    return jsonify({'games': ['game24']})

@core_bp.route('/api/debug/assets')
def debug_assets():
    """Debug endpoint to check asset status"""
    from shared_state import ASSETS_DIR, ANSWERS_PATH

    themes = []
    if ASSETS_DIR.exists():
        themes = [d.name for d in ASSETS_DIR.iterdir() if d.is_dir()]

    return jsonify({
        'answers_file_exists': ANSWERS_PATH.exists(),
        'assets_dir_exists': ASSETS_DIR.exists(),
        'available_themes': themes,
        'answers_path': str(ANSWERS_PATH),
        'assets_path': str(ASSETS_DIR)
    })


@core_bp.route('/')
def index():
    """Serve the main index.html file"""
    return send_file('static/index.html')

@core_bp.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

@core_bp.route('/api/games')
def list_games():
    """List available games"""
    return jsonify({'games': ['game24']})

# Keep these for backward compatibility with your JavaScript
@core_bp.route('/api/next')
def api_next():
    """Redirect to game24 endpoint for backward compatibility"""
    from flask import redirect, request
    return redirect(f'/api/game24/next?{request.query_string.decode()}')

@core_bp.route('/api/check', methods=['POST'])
def api_check():
    """Redirect to game24 endpoint for backward compatibility"""
    from flask import redirect, request
    # For POST requests, we need to handle differently
    # This is a simplified version - you might need to proxy the request
    return redirect(f'/api/game24/check?{request.query_string.decode()}')

@core_bp.route('/api/help', methods=['POST'])
def api_help():
    """Redirect to game24 endpoint for backward compatibility"""
    from flask import redirect, request
    return redirect(f'/api/game24/help?{request.query_string.decode()}')

# Add other backward compatibility endpoints as needed
@core_bp.route('/api/pool', methods=['POST'])
def api_pool():
    from flask import redirect, request
    return redirect(f'/api/game24/pool?{request.query_string.decode()}')

@core_bp.route('/api/pool_report')
def api_pool_report():
    from flask import redirect, request
    return redirect(f'/api/game24/pool_report?{request.query_string.decode()}')

