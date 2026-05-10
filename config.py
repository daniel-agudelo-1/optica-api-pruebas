import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Base de datos
    DATABASE_URL = os.environ.get('DATABASE_URL', '')

    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    if DATABASE_URL and DATABASE_URL.startswith('postgresql://'):
        DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://', 1)

    if DATABASE_URL and 'sslmode' not in DATABASE_URL:
        DATABASE_URL += '?sslmode=require'

    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///optica.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 20,
        "max_overflow": 0
    }

    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')

    if not SECRET_KEY:
        raise ValueError("❌ SECRET_KEY no está definida en el .env")
    if not JWT_SECRET_KEY:
        raise ValueError("❌ JWT_SECRET_KEY no está definida en el .env")

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)

    # Brevo (Email Service)
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
    #BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', 'noreply@visualoutlet.com')
    BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'Visual Outlet')