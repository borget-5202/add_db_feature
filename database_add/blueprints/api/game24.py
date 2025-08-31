from flask import Blueprint, request, jsonify, session
from lib.database import db
from lib.database.models import GameSession, GameData
from lib.games.game24_utils import init_shared_state, get_pools_adv
from datetime import datetime
import uuid
import random,json
from lib.auth import login_required, get_current_user

game24_bp = Blueprint('game24', __name__)

# Initialize shared state when blueprint is loaded
init_shared_state()
POOLS_ADV = get_pools_adv()

@game24_bp.route('/demo', methods=['POST'])
# No @login_required decorator = no authentication needed
def start_demo():
    """Start demo mode - no authentication required"""
    return jsonify({'message': 'Demo mode started'}), 200

@game24_bp.route('/start_session', methods=['POST'])
@login_required  
def start_session():
    """Start a new Game24 session"""
    try:
        current_user = get_current_user()

        # Create session in database
        session_obj = GameSession(
            session_uuid=str(uuid.uuid4()),
            user_id=current_user.id,  # Use the authenticated user
            game_id=1,  # Assuming game24 has ID 1
            current_game='game24',
            created_at=datetime.utcnow()
        )

        db.session.add(session_obj)
        db.session.commit()

        # Store session ID in flask session
        session['game_session_id'] = session_obj.id

        return jsonify({
            'session_id': session_obj.id,
            'session_uuid': session_obj.session_uuid,
            'message': 'Game24 session started'
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@game24_bp.route('/get_puzzle', methods=['GET'])
@login_required  
def get_puzzle():
    """Get a random puzzle based on difficulty"""
    try:
        difficulty = request.args.get('difficulty', 'medium')
        puzzles = POOLS_ADV.get(difficulty, [])  # Now 'easy', 'medium', 'hard' work directly

        if not puzzles:
            return jsonify({'error': f'No puzzles found for difficulty: {difficulty}'}), 404

        import random
        puzzle_tuple = random.choice(puzzles)
        puzzle_data = puzzle_tuple[0]  # Get the puzzle dict from tuple

        return jsonify({
            'puzzle_id': puzzle_data['case_id'],
            'cards': puzzle_data['cards'],
            'difficulty': puzzle_data.get('level', difficulty)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


#efficient version
@game24_bp.route('/check_answer', methods=['POST'])
@login_required
def check_answer():
    try:
        data = request.get_json()
        puzzle_id = data.get('puzzle_id')
        user_answer = data.get('answer')

        is_correct = True  # Your validation logic

        current_user = get_current_user()
        current_user.game24_total_attempts += 1

        if is_correct:
            current_user.game24_correct_attempts += 1
            current_user.game24_total_score += 10

        current_user.game24_last_played = datetime.utcnow()

        # Check if we have a game session, if not create one
        game_session_id = session.get('game_session_id')
        if not game_session_id:
            # Create a new game session
            game_session = GameSession(
                session_uuid=str(uuid.uuid4()),
                user_id=current_user.id,
                game_id=1,  # Assuming game24 has ID 1
                start_time=datetime.utcnow()
            )
            db.session.add(game_session)
            db.session.flush()  # Get the ID without committing
            game_session_id = str(game_session.id)
            session['game_session_id'] = game_session_id

        # Now save with valid session_id
        game_data = GameData(
            session_id=game_session_id,  # Now this won't be null
            game_name='game24',
            data_type='attempt',
            data=json.dumps({
                'puzzle_id': puzzle_id,
                'user_answer': user_answer,
                'is_correct': is_correct,
                'timestamp': datetime.utcnow().isoformat()
            })
        )
        db.session.add(game_data)
        db.session.commit()

        return jsonify({
            'correct': is_correct,
            'message': 'Answer checked successfully',
            'score_added': 10 if is_correct else 0,
            'new_total_score': current_user.game24_total_score
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@game24_bp.route('/stats', methods=['GET'])
@login_required  
def get_stats():
    """Get user statistics for Game24"""
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        # Get user's game data
        user_data = GameData.query.filter_by(
            session_id=session.get('session_id'),
            game_name='game24'
        ).all()
        
        # Calculate basic stats
        total_attempts = len(user_data)
        correct_attempts = sum(1 for d in user_data if d.data.get('is_correct'))
        
        return jsonify({
            'total_attempts': total_attempts,
            'correct_attempts': correct_attempts,
            'accuracy': correct_attempts / total_attempts if total_attempts > 0 else 0
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Add this debug route to see what POOLS_ADV contains
@game24_bp.route('/debug_pools', methods=['GET'])
def debug_pools():
    """Debug endpoint to check POOLS_ADV structure"""
    try:
        return jsonify({
            'pool_keys': list(POOLS_ADV.keys()) if POOLS_ADV else 'None',
            'medium_pool_type': type(POOLS_ADV.get('medium', 'Not found')),
            'medium_pool_sample': POOLS_ADV.get('medium', [])[:1] if POOLS_ADV.get('medium') else 'Empty'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e), 'type': type(e).__name__}), 500


# Add this debug route to see what's really happening
@game24_bp.route('/debug_pools_detailed', methods=['GET'])
def debug_pools_detailed():
    """Detailed debug endpoint"""
    try:
        # Check what POOLS_ADV actually is
        pools_type = type(POOLS_ADV)
        pools_repr = repr(POOLS_ADV)

        # Check if it's callable (like a function/class)
        is_callable = callable(POOLS_ADV)

        # Try to see if it has the expected structure
        if hasattr(POOLS_ADV, 'get'):
            sample_data = list(POOLS_ADV.keys())[:3] if POOLS_ADV else 'Empty'
        else:
            sample_data = 'Not a dictionary'

        return jsonify({
            'pools_type': str(pools_type),
            'pools_repr': pools_repr,
            'is_callable': is_callable,
            'sample_data': sample_data
        }), 200

    except Exception as e:
        return jsonify({'error': str(e), 'type': type(e).__name__}), 500


# blueprints/api/game24.py - UPDATE check_solution route
@game24_bp.route('/check_solution', methods=['POST'])
@login_required
def check_solution():
    """Check if the user's solution is correct and update scores"""
    try:
        data = request.get_json()
        puzzle_id = data.get('puzzle_id')
        user_solution = data.get('solution')

        # Your solution validation logic here
        is_correct = validate_solution(puzzle_id, user_solution)

        # Get current user
        current_user = get_current_user()

        # Update user scores in database
        current_user.game24_total_puzzles += 1

        if is_correct:
            current_user.game24_correct_puzzles += 1
            current_user.game24_total_score += 10  # 10 points per correct puzzle
            # TODO: Implement streak calculation

        db.session.commit()

        # Save attempt to game data
        game_data = GameData(
            session_id=session.get('game_session_id'),
            game_name='game24',
            data_type='attempt',
            data={
                'puzzle_id': puzzle_id,
                'user_solution': user_solution,
                'is_correct': is_correct,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
        db.session.add(game_data)
        db.session.commit()

        return jsonify({
            'correct': is_correct,
            'message': 'Solution checked successfully',
            'score_added': 10 if is_correct else 0,
            'new_total_score': current_user.game24_total_score
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
