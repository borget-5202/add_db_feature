# web/config.py - UPDATED CONFIG
import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://littleteachers:littlelove@localhost/wearelittleteachers'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session settings
    SESSION_COOKIE_SECURE = False  # True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Template and static files
    TEMPLATES_AUTO_RELOAD = True

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Log SQL queries

class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
