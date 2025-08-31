import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///wearelittleteachers.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Platform
    PLATFORM_NAME = os.getenv('PLATFORM_NAME', 'WeAreLittleTeachers')
    DEBUG = os.getenv('FLASK_ENV', 'development') == 'development'
