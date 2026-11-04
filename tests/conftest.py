import pytest
from flask import g

from app import create_app
from app.extensions import db
from app.routes.auth import reset_login_attempts
from config import TestConfig
from tests.factories import PASSWORD


@pytest.fixture
def app(tmp_path):
    """A fresh app + temporary database for EVERY test (your demo DB is never touched)."""
    app = create_app(TestConfig, {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}"})
    @app.before_request
    def _fresh_login_state():
        # Tests keep ONE app context open for factories; Flask-Login caches the user on `g`,
        # so clear it before every request to behave like the real server.
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        reset_login_attempts()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, user, password=PASSWORD, follow=False):
    return client.post("/login", data={"email": user.email, "password": password}, follow_redirects=follow)


@pytest.fixture
def login_as(app):
    """login_as(user) -> a NEW logged-in test client for that user."""
    def _login(user):
        c = app.test_client()
        resp = login(c, user)
        assert resp.status_code == 302, "login failed in test setup"
        return c
    return _login
