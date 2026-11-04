"""Entry point:  python run.py"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000,
            debug=os.environ.get("FLASK_DEBUG", "0") == "1")

