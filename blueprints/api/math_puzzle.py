# blueprints/api/math_puzzle.py (future game example)
from flask import Blueprint
from lib.auth import login_required

math_puzzle_bp = Blueprint('math_puzzle', __name__)

@math_puzzle_bp.route('/start', methods=['POST'])
@login_required  # Just add this decorator
def start_math_puzzle():
    """Start math puzzle - automatically authenticated!"""
    try:
        current_user = get_current_user()
        # Your game logic here
        return jsonify({'message': 'Math puzzle started'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
