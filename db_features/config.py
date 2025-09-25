import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///arcade.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = True

    # Password reset
    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT", "dev-salt-change-me")
    PASSWORD_RESET_TOKEN_AGE = int(os.environ.get("PASSWORD_RESET_TOKEN_AGE", "3600"))  # 1 hour

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    
    RATELIMIT_DEFAULT = "200 per hour; 50 per minute"

    TARGETS_ENABLED = [24, 10, 36]
    SOLVABLE_ONLY = False  # you can turn this on later
