"""Configuration is explicit; production never inherits development secrets."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
ENV = os.getenv('APP_ENV', 'development')
PRODUCTION = ENV == 'production'
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./village-v2.db').replace('postgres://', 'postgresql://', 1)
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://', 1)
APP_SECRET = os.getenv('APP_SECRET', 'local-development-only-change-before-production')
WEB_URL = os.getenv('WEB_URL', 'http://localhost:3000').rstrip('/')
ALLOWED_ORIGINS = [x.strip() for x in os.getenv('ALLOWED_ORIGINS', WEB_URL + ',http://localhost:8000,capacitor://localhost,http://localhost,https://localhost').split(',') if x.strip()]
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_FROM = os.getenv('SMTP_FROM', 'Village <hello@example.com>')
SMTP_TLS = os.getenv('SMTP_TLS', 'true') == 'true'
VERIFY_EMAIL = PRODUCTION or os.getenv('VERIFY_EMAIL', 'false') == 'true'
SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', 'support@example.com')
FIREBASE_CREDENTIALS = os.getenv('FIREBASE_CREDENTIALS_JSON', '')
if PRODUCTION:
    if len(APP_SECRET) < 40 or APP_SECRET.startswith('local-development'):
        raise RuntimeError('Set a random APP_SECRET of at least 40 characters.')
    if not DATABASE_URL.startswith('postgresql'):
        raise RuntimeError('Production requires PostgreSQL.')
    if not WEB_URL.startswith('https://') or not (SMTP_HOST or RESEND_API_KEY) or SUPPORT_EMAIL.endswith('@example.com'):
        raise RuntimeError('Production requires HTTPS WEB_URL, SMTP_HOST or RESEND_API_KEY, and real SUPPORT_EMAIL.')
