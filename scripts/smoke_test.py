"""Optional end-to-end check with REAL CSRF protection and all four roles.

Usage:  python scripts/smoke_test.py
Builds a throw-away database in your temp folder (your demo database is not touched),
seeds it, logs in as every role and opens every main page.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import g  # noqa: E402

from app import create_app  # noqa: E402
from config import Config  # noqa: E402
from scripts.seed_demo_data import seed  # noqa: E402


def main():
    tmp = Path(tempfile.mkdtemp()) / "smoke.db"
    app = create_app(Config, {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp.as_posix()}"})
    seed(app)

    @app.before_request
    def _forget_cached_user():          # one long app context is used here, so clear per-request caches
        g.pop("_login_user", None)
        g.pop("csrf_token", None)

    def token(html):
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="csrf_token"', html.decode())
        return m.group(1) or m.group(2)

    def session(email):
        c = app.test_client()
        r = c.post("/login", data={"email": email, "password": app.config["DEMO_PASSWORD"],
                                   "csrf_token": token(c.get("/login").data)})
        assert r.status_code == 302, f"login failed for {email}"
        return c

    pages = {
        "admin@hospital.demo": ["/admin/", "/admin/patients", "/admin/doctors", "/admin/nurses", "/admin/appointments",
                                "/admin/rooms", "/admin/medicines", "/admin/emergency", "/admin/billing", "/admin/insurance",
                                "/admin/discharges", "/admin/billing/1"],
        "doctor@hospital.demo": ["/doctor/", "/doctor/appointments", "/doctor/reports", "/doctor/patients/2"],
        "nurse@hospital.demo": ["/nurse/", "/nurse/patients/2"],
        "patient@hospital.demo": ["/patient/", "/patient/doctors", "/patient/appointments", "/patient/treatment",
                                  "/patient/reports", "/patient/invoices", "/patient/profile"],
        "patient2@hospital.demo": ["/patient/treatment", "/patient/invoices", "/patient/reports/1"],
    }
    failures = 0
    with app.app_context():
        for email, urls in pages.items():
            client = session(email)
            for url in urls:
                status = client.get(url).status_code
                print(("OK  " if status == 200 else "FAIL"), email.split("@")[0].ljust(9), url, status)
                failures += status != 200
        admin = session("admin@hospital.demo")
        pdf = admin.get("/documents/invoice/1.pdf")
        print("OK  " if pdf.data.startswith(b"%PDF") else "FAIL", "invoice PDF", len(pdf.data), "bytes")
        failures += not pdf.data.startswith(b"%PDF")
        blocked = session("patient@hospital.demo").get("/documents/invoice/1.pdf").status_code
        print("OK  " if blocked == 403 else "FAIL", "other patient's invoice blocked ->", blocked)
        failures += blocked != 403
    print("\nSmoke test:", "PASSED" if not failures else f"{failures} FAILURE(S)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
