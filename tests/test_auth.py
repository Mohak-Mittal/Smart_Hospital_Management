from app.models import User
from tests.conftest import login
from tests.factories import PASSWORD, make_admin, make_doctor, make_nurse, make_patient


def test_registration_and_login(client):
    resp = client.post("/register", data={"name": "New Person", "email": "New@Test.demo", "password": "Strong123",
                                          "confirm": "Strong123"}, follow_redirects=False)
    assert resp.status_code == 302 and "/patient/" in resp.headers["Location"]
    user = User.query.filter_by(email="new@test.demo").first()
    assert user and user.role == "patient" and user.patient_profile.patient_code.startswith("PAT-")
    client.post("/logout")
    assert login(client, user, "Strong123").status_code == 302


def test_password_is_hashed_not_plaintext(app):
    p = make_patient()
    assert p.user.password_hash != PASSWORD and PASSWORD not in p.user.password_hash


def test_registration_validation_errors(client):
    resp = client.post("/register", data={"name": "X", "email": "bad", "password": "short", "confirm": "different"})
    assert resp.status_code == 200 and b"Invalid email" in resp.data or b"valid email" in resp.data.lower()
    assert User.query.count() == 0


def test_duplicate_email_rejected(client):
    make_patient(email="dup@test.demo")
    resp = client.post("/register", data={"name": "Dup Two", "email": "dup@test.demo", "password": "Strong123", "confirm": "Strong123"})
    assert b"already exists" in resp.data


def test_wrong_password_and_inactive_user(client):
    p = make_patient()
    assert b"Invalid email or password" in login(client, p.user, "nope", follow=True).data
    p.user.active = False
    from app.extensions import db
    db.session.commit()
    assert b"Invalid email or password" in login(client, p.user, follow=True).data


def test_each_role_lands_on_its_dashboard(app):
    for user, prefix in [(make_patient().user, "/patient/"), (make_doctor().user, "/doctor/"),
                         (make_nurse().user, "/nurse/"), (make_admin(), "/admin/")]:
        c = app.test_client()
        resp = login(c, user)
        assert resp.headers["Location"].endswith(prefix), (user.role, resp.headers["Location"])
        assert c.get(prefix).status_code == 200


def test_login_rate_limit(client):
    p = make_patient()
    for _ in range(5):
        login(client, p.user, "wrong")
    resp = login(client, p.user, PASSWORD)           # correct password, but locked out
    assert resp.status_code == 429


def test_open_redirect_is_blocked(client):
    p = make_patient()
    resp = client.post("/login?next=https://evil.example/", data={"email": p.user.email, "password": PASSWORD})
    assert "evil.example" not in resp.headers["Location"]


def test_protected_page_redirects_to_login(client):
    resp = client.get("/patient/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_logout_requires_post(app):
    p = make_patient()
    c = app.test_client()
    login(c, p.user)
    assert c.get("/logout").status_code == 405
    c.post("/logout")
    assert c.get("/patient/").status_code == 302
