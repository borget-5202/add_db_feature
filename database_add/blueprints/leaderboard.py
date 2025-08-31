# blueprints/leaderboard.py
from flask import Blueprint, jsonify
from lib.database import db
from lib.database.models import User
from lib.auth import login_required

leaderboard_bp = Blueprint('leaderboard', __name__)

@leaderboard_bp.route('/game24', methods=['GET'])
def game24_leaderboard():
    """Get Game24 leaderboard"""
    try:
        # Get top 10 players by score
        top_players = User.query.filter(
            User.game24_total_score > 0
        ).order_by(
            User.game24_total_score.desc()
        ).limit(10).all()
        
        leaderboard = []
        for user in top_players:
            accuracy = (user.game24_correct_puzzles / user.game24_total_puzzles * 100) if user.game24_total_puzzles > 0 else 0
            
            leaderboard.append({
                'username': user.username,
                'total_score': user.game24_total_score,
                'total_puzzles': user.game24_total_puzzles,
                'correct_puzzles': user.game24_correct_puzzles,
                'accuracy': round(accuracy, 1),
                'max_streak': user.game24_max_streak
            })
        
        return jsonify({'leaderboard': leaderboard}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@leaderboard_bp.route('/my-stats', methods=['GET'])
@login_required
def my_stats():
    """Get current user's stats"""
    try:
        from flask import session
        user = User.query.get(session['user_id'])
        
        if user:
            accuracy = (user.game24_correct_puzzles / user.game24_total_puzzles * 100) if user.game24_total_puzzles > 0 else 0
            
            return jsonify({
                'username': user.username,
                'total_score': user.game24_total_score,
                'total_attempts': user.game24_total_attempts,
                'total_correct_attempts': user.game24_correct_attempts,
                'total_puzzles': user.game24_total_puzzles,
                'correct_puzzles': user.game24_correct_puzzles,
                'accuracy': round(accuracy, 1),
                'max_streak': user.game24_max_streak,
                'rank': 'Coming soon'  # You can implement ranking logic later
            }), 200
            
        return jsonify({'error': 'User not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
