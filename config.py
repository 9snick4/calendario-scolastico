import os

class Config:
    SECRET_KEY = "supersegreto"
    SQLALCHEMY_DATABASE_URI = "sqlite:///instance/orario_scolastico.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
