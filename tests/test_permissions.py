from app.extensions import db
from app.models import MedicalReport
from app.services import billing_service, treatment_service
from app.utils.timeutil import hospital_now
from tests.factories import make_admin, make_doctor, make_nurse, make_patient, paid_appointment


def _report(patient, doctor, published=True):
    r = MedicalReport(report_code=f"REP-T{MedicalReport.query.count()}", patient_id=patient.id, doctor_id=doctor.id,
                      title="Demo <b>report</b>", content="Content & <script>alert(1)</script>",
                      status="published" if published else "draft", published_at=hospital_now() if published else None)
    db.session.add(r)
    db.session.commit()
    return r


def _bill(patient, doctor, admin):
    plan = treatment_service.create_plan(doctor, patient, "medicine", "Dx", "", {"medicine_charges": "1200"})
    treatment_service.set_status(plan, "in_progress", doctor.user)
    return billing_service.create_bill(patient, admin, False, [])


def test_patient_cannot_view_another_patients_records(app, login_as):
    a, b, d, admin = make_patient(), make_patient(), make_doctor(), make_admin()
    report, bill = _report(a, d), _bill(a, d, admin)
    cb = login_as(b.user)
    for url in (f"/patient/reports/{report.id}", f"/documents/report/{report.id}.pdf", f"/documents/invoice/{bill.id}",
                f"/documents/invoice/{bill.id}.pdf", f"/payments/bill/{bill.id}"):
        assert cb.get(url).status_code == 403, url
    # and the lists only contain their own data
    assert b"&lt;b&gt;report" not in cb.get("/patient/reports").data


def test_patient_can_download_only_own_invoice_and_report(app, login_as):
    a, d, admin = make_patient(), make_doctor(), make_admin()
    report, bill = _report(a, d), _bill(a, d, admin)
    ca = login_as(a.user)
    r = ca.get(f"/documents/invoice/{bill.id}.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    r = ca.get(f"/documents/report/{report.id}.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    assert ca.get(f"/documents/invoice/{bill.id}").status_code == 200          # printable HTML fallback


def test_unpublished_report_hidden_from_patient_but_not_author(app, login_as):
    a, d = make_patient(), make_doctor()
    draft = _report(a, d, published=False)
    assert login_as(a.user).get(f"/patient/reports/{draft.id}").status_code == 403
    assert login_as(a.user).get(f"/documents/report/{draft.id}.pdf").status_code == 403
    assert login_as(d.user).get(f"/documents/report/{draft.id}.pdf").status_code == 200
    assert login_as(make_doctor().user).get(f"/documents/report/{draft.id}.pdf").status_code == 403


def test_user_content_is_escaped_in_html_and_pdf_builds(app, login_as):
    a, d = make_patient(), make_doctor()
    r = _report(a, d)
    html = login_as(a.user).get(f"/patient/reports/{r.id}").data
    assert b"<script>alert(1)</script>" not in html and b"&lt;script&gt;" in html
    from app.utils.pdf_generator import build_report_pdf
    assert build_report_pdf(r, "Hosp").startswith(b"%PDF")        # markup characters don't break the PDF


def test_doctor_cannot_access_unassigned_patient(app, login_as):
    d1, d2, p = make_doctor(), make_doctor(), make_patient()
    paid_appointment(p, d1)
    assert login_as(d2.user).get(f"/doctor/patients/{p.id}").status_code == 403
    assert login_as(d1.user).get(f"/doctor/patients/{p.id}").status_code == 200
    # write actions are blocked too
    c2 = login_as(d2.user)
    assert c2.post(f"/doctor/patients/{p.id}/reports", data={"r-title": "x", "r-content": "y"}).status_code == 403
    assert c2.post(f"/doctor/patients/{p.id}/treatments", data={}).status_code == 403


def test_pending_unpaid_booking_does_not_grant_doctor_access(app, login_as):
    from app.services import appointment_service
    from tests.factories import free_slot
    d, p = make_doctor(), make_patient()
    appointment_service.book_appointment(p, d, free_slot(d))
    assert login_as(d.user).get(f"/doctor/patients/{p.id}").status_code == 403


def test_doctor_cannot_touch_another_doctors_treatment_or_report(app, login_as):
    d1, d2, p, admin = make_doctor(), make_doctor(), make_patient(), make_admin()
    paid_appointment(p, d1)
    plan = treatment_service.create_plan(d1, p, "medicine", "Dx", "", {"medicine_charges": "100"})
    rep = _report(p, d1, published=False)
    c2 = login_as(d2.user)
    assert c2.post(f"/doctor/treatments/{plan.id}/status", data={"status": "in_progress"}).status_code == 403
    assert c2.post(f"/doctor/reports/{rep.id}/publish").status_code == 403
    assert login_as(d1.user).post(f"/doctor/reports/{rep.id}/publish").status_code == 302
    assert db.session.get(MedicalReport, rep.id).is_published


def test_role_walls(app, login_as):
    p, d, n, admin = make_patient(), make_doctor(), make_nurse(), make_admin()
    cp, cd, cn, ca = login_as(p.user), login_as(d.user), login_as(n.user), login_as(admin)
    for url in ("/admin/", "/admin/patients", "/admin/billing", "/doctor/", "/nurse/"):
        assert cp.get(url).status_code == 403, url
    for url in ("/admin/", "/admin/emergency", "/patient/", "/nurse/"):
        assert cd.get(url).status_code == 403, url
    for url in ("/admin/", "/doctor/", "/patient/"):
        assert cn.get(url).status_code == 403, url
    for url in ("/patient/", "/doctor/", "/nurse/"):
        assert ca.get(url).status_code == 403, url
    assert cp.post("/admin/discharges/1").status_code == 403


def test_nurse_only_sees_assigned_patients(app, login_as):
    n, p1, p2, d = make_nurse(), make_patient(), make_patient(), make_doctor()
    n.assigned_patients.append(p1)
    db.session.commit()
    plan = treatment_service.create_plan(d, p1, "medicine", "Dx", "", {"medicine_charges": "100"})
    c = login_as(n.user)
    assert c.get(f"/nurse/patients/{p1.id}").status_code == 200
    assert c.get(f"/nurse/patients/{p2.id}").status_code == 403
    assert c.post(f"/nurse/treatments/{plan.id}/note", data={"n-note": "Vitals ok"}).status_code == 302
    other = treatment_service.create_plan(d, p2, "medicine", "Dx", "", {"medicine_charges": "100"})
    assert c.post(f"/nurse/treatments/{other.id}/note", data={"n-note": "x"}).status_code == 403


def test_csrf_is_enforced_when_enabled(tmp_path):
    from app import create_app
    from config import TestConfig
    app = create_app(TestConfig, {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'c.db').as_posix()}", "WTF_CSRF_ENABLED": True})
    with app.app_context():
        db.create_all()
        resp = app.test_client().post("/login", data={"email": "a@b.co", "password": "x"})
        assert resp.status_code == 403 and b"expired" in resp.data
        db.session.remove(); db.engine.dispose()


def test_error_pages(client):
    assert client.get("/no-such-page").status_code == 404 and b"Page not found" in client.get("/no-such-page").data


def test_security_headers(client):
    r = client.get("/login")
    assert r.headers["X-Frame-Options"] == "DENY" and "script-src 'self'" in r.headers["Content-Security-Policy"]
