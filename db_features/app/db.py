# app/db.py or app/__init__.py (where you init SQLAlchemy)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

db = SQLAlchemy(metadata=MetaData(schema="app"))


#db = SQLAlchemy()
