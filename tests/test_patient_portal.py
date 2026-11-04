from datetime import timedelta

from app.extensions import db
from app.utils.timeutil import hospital_now
from tests.factories import free_slot, make_admin, make_doctor, make_patient, make_policy, paid_appointment


def test_all_patient_pages_render(app, login_as):
    p, d = make_patient(), make_doctor()
    make_policy(p)
    paid_appointment(p, d)
    c = login_as(p.user)
    for url in ("/patient/", "/patient/doctors", f"/patient/doctors/{d.id}", "/patient/appointments",
                "/patient/appointments?tab=pending", "/patient/appointments?tab=all", "/patient/treatment",
                "/patient/reports", "/patient/invoices", "/patient/profile", "/auth/none" if False else "/account/password"):
        assert c.get(url).status_code == 200, url


def test_doctor_search_filters(app, login_as):
    p = make_patient()
    make_doctor("general", name="Gina General")
    make_doctor("cardiologist", name="Carl Cardio")
    c = login_as(p.user)
    assert b"Carl Cardio" in c.get("/patient/doctors?q=cardio").data
    assert b"Gina General" not in c.get("/patient/doctors?q=cardio").data
    cheap = c.get("/patient/doctors?max_fee=600").data
    assert b"Gina General" in cheap and b"Carl Cardio" not in cheap
    assert b"No doctors match" in c.get("/patient/doctors?q=zzzz").data


def test_doctor_detail_shows_fee_and_slots(app, login_as):
    p, d = make_patient(), make_doctor("neurologist")
    html = login_as(p.user).get(f"/patient/doctors/{d.id}?date={free_slot(d).date().isoformat()}").data
    assert b"1,800.00" in html and b"Reserve slot" in html


def test_full_booking_flow_through_the_ui(app, login_as):
    p, d = make_patient(), make_doctor()
    c = login_as(p.user)
    slot = free_slot(d)
    resp = c.post("/appointments/book", data={"doctor_id": d.id, "slot": slot.strftime("%Y-%m-%dT%H:%M"), "reason": "cough"}, follow_redirects=True)
    assert b"Complete the demo payment" in resp.data and b"NO REAL MONEY" in resp.data
    from app.models import Appointment
    appt = Appointment.query.one()
    resp = c.post(f"/payments/appointment/{appt.id}", data={"method": "upi", "upi_id": "me@bank"}, follow_redirects=True)
    assert b"Payment receipt" in resp.data and b"confirmed" in resp.data
    db.session.expire_all()
    assert Appointment.query.one().status == "scheduled"
    assert b"Scheduled" in c.get("/patient/appointments").data


def test_failed_payment_message_and_no_confirmation(app, login_as):
    p, d = make_patient(), make_doctor()
    c = login_as(p.user)
    slot = free_slot(d)
    c.post("/appointments/book", data={"doctor_id": d.id, "slot": slot.strftime("%Y-%m-%dT%H:%M")})
    from app.models import Appointment
    appt = Appointment.query.one()
    resp = c.post(f"/payments/appointment/{appt.id}", data={"method": "upi", "upi_id": "me@fail"}, follow_redirects=True)
    assert b"declined" in resp.data
    db.session.expire_all()
    assert Appointment.query.one().status == "pending"


def test_profile_update_and_encapsulated_fields(app, login_as):
    p = make_patient()
    c = login_as(p.user)
    resp = c.post("/patient/profile", data={"phone": "+91 98765 43210", "gender": "Female", "blood_group": "O+", "address": "1 Road",
                                            "emergency_contact": "Mom", "medical_history": "Demo: none"}, follow_redirects=True)
    assert b"Profile saved" in resp.data
    db.session.expire_all()
    assert p.blood_group == "O+" and p.medical_history == "Demo: none"
    assert not hasattr(p, "__medical_history")       # name-mangled: really stored as _Patient__medical_history
    assert hasattr(p, "_Patient__medical_history")   # (documented: mangling is NOT security)
    bad = c.post("/patient/profile", data={"phone": "abc", "gender": "", "blood_group": ""})
    assert b"valid phone" in bad.data


def test_wallet_cannot_go_negative(app):
    import pytest
    p = make_patient()
    p.credit_wallet(100)
    with pytest.raises(ValueError):
        p.debit_wallet(200)
    assert p.debit_wallet(40) == 60


def test_admin_pages_all_render(app, login_as):
    from app.services import emergency_service
    admin, d, p = make_admin(), make_doctor(), make_patient()
    paid_appointment(p, d)
    emergency_service.add_case("Walk In", "pain", 2)
    c = login_as(admin)
    for url in ("/admin/", "/admin/patients", f"/admin/patients/{p.id}/edit", "/admin/doctors", "/admin/doctors/new",
                f"/admin/doctors/{d.id}/edit", "/admin/nurses", "/admin/nurses/new", "/admin/appointments", "/admin/rooms",
                "/admin/rooms/new", "/admin/medicines", "/admin/medicines/new", "/admin/emergency", "/admin/emergency/new",
                "/admin/billing", "/admin/billing/new", "/admin/insurance", "/admin/insurance/new", "/admin/discharges"):
        assert c.get(url).status_code == 200, url


def test_admin_can_create_doctor_and_change_fee(app, login_as):
    from app.models import Doctor, Specialization, User
    from tests.factories import ensure_reference_data
    ensure_reference_data()
    admin = make_admin()
    c = login_as(admin)
    spec = Specialization.query.filter_by(policy_key="surgeon").first()
    resp = c.post("/admin/doctors/new", data={"name": "Dina Doc", "email": "dina@test.demo", "password": "Strong123", "specialization_id": spec.id,
                                              "working_days": ["0", "1"], "start_time": "09:00", "end_time": "13:00", "slot_minutes": 30,
                                              "accepting_appointments": "y", "active": "y", "experience_years": 3}, follow_redirects=True)
    assert b"Doctor created" in resp.data
    doc = Doctor.query.one()
    assert doc.doctor_code.startswith("DOC-") and doc.working_days == "0,1" and doc.calculate_consultation_fee() == 2500
    c.post(f"/admin/specializations/{spec.id}/edit", data={"base_fee": "2750"})
    db.session.expire_all()
    assert doc.calculate_consultation_fee() == 2750
    c.post(f"/admin/doctors/{doc.id}/toggle")
    db.session.expire_all()
    assert not doc.user.active
