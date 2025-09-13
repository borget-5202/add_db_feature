from flask import session, jsonify
from functools import wraps
from lib.database.models import User

def init_auth(app):
    """Initialize authentication system"""
    # Any auth-related initialization can go here
    # For example: setup session settings, load auth providers, etc.
    pass

def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get the current authenticated user from session"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def get_current_user_id():
    """Get the current user ID from session"""
    return session.get('user_id')

def is_authenticated():
    """Check if user is authenticated"""
    return 'user_id' in session

# Optional: Admin role check
def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
            
        return f(*args, **kwargs)
    return decorated_function
