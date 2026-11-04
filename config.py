"""Application configuration.

Settings come from environment variables (see .env.example) with safe
LOCAL-DEVELOPMENT defaults.  Never use the default SECRET_KEY in production.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:  # python-dotenv is optional: .env is only a convenience
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-secret-change-me"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + (BASE_DIR / "instance" / "hospital.db").as_posix()
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True

    # --- Time: every date/time in the app is HOSPITAL LOCAL time (naive). ---
    HOSPITAL_TIMEZONE = os.environ.get("HOSPITAL_TIMEZONE") or "Asia/Kolkata"

    # --- Business rules (documented in docs/USER_GUIDE.md) ---
    SLOT_HOLD_MINUTES = 15          # unpaid booking holds a slot for this long
    BOOKING_WINDOW_DAYS = 30        # how far ahead patients may book
    CANCEL_CUTOFF_HOURS = 2         # patients cannot cancel closer than this
    FULL_REFUND_HOURS = 24          # >= this many hours ahead: 100% refund, else 50%
    LOGIN_MAX_ATTEMPTS = 5          # failed logins before a temporary lock
    LOGIN_LOCKOUT_SECONDS = 300
    PER_PAGE = 10

    # --- Demo only ---
    DEMO_PASSWORD = "Demo@12345"
    HOSPITAL_NAME = "CityCare Demo Hospital"


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    LOGIN_MAX_ATTEMPTS = 5
