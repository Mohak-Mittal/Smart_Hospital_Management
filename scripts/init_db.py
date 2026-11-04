"""Create all database tables.   Usage:  python scripts/init_db.py [--reset]

--reset  deletes the existing tables first (ALL DATA IS LOST).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


def init_db(reset: bool = False):
    app = create_app()
    with app.app_context():
        if reset:
            db.drop_all()
            print("Dropped all tables.")
        db.create_all()
        print(f"Database ready: {app.config['SQLALCHEMY_DATABASE_URI']}")


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv)
