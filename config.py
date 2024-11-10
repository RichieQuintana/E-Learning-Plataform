# config.py
import os

class Config:
    SECRET_KEY = 'supersecretkey'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'  # Asegúrate de que el URI esté correcto
    SQLALCHEMY_TRACK_MODIFICATIONS = False
