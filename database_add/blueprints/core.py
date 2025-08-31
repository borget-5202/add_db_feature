# blueprints/core.py - CORE_BP (main routes)
from flask import Blueprint, render_template, jsonify, session
from lib.auth import login_required

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def homepage():
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('index.html')

@core_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@core_bp.route('/games')
def games_list():
    return render_template('games.html')

@core_bp.route('/health')
def health_check():
    return {'status': 'healthy', 'message': 'WeAreLittleTeachers is running'}

@core_bp.route('/')
def index():
    """Main landing page"""
    return render_template('index.html')

@core_bp.route('/api/info')
def api_info():
    """API information endpoint"""
    return jsonify({
        'name': 'WeAreLittleTeachers API',
        'version': '1.0',
        'description': 'Educational games platform API'
    })

@core_bp.route('/play/game24')
@login_required
def play_game24():
    """Game24 play page"""
    return render_template('games/game24.html')
