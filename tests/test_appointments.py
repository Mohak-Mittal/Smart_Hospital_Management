from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Appointment
from app.services import appointment_service
from app.services.appointment_service import BookingError
from app.utils.timeutil import hospital_now
from tests.factories import free_slot, make_admin, make_doctor, make_patient, paid_appointment


def test_booking_available_slot_succeeds(app):
    p, d = make_patient(), make_doctor()
    appt = appointment_service.book_appointment(p, d, free_slot(d), "checkup")
    assert appt.status == "pending" and appt.payment_status == "pending"
    assert appt.fee == d.calculate_consultation_fee() and appt.code.startswith("APT-")


def test_double_booking_same_slot_rejected(app):
    p1, p2, d = make_patient(), make_patient(), make_doctor()
    slot = free_slot(d)
    appointment_service.book_appointment(p1, d, slot)
    with pytest.raises(BookingError, match="booked"):
        appointment_service.book_appointment(p2, d, slot)
    assert Appointment.query.filter_by(doctor_id=d.id, start_time=slot).count() == 1


def test_database_index_blocks_duplicate_even_if_service_is_bypassed(app):
    from sqlalchemy.exc import IntegrityError
    p, d = make_patient(), make_doctor()
    slot = free_slot(d)
    appointment_service.book_appointment(p, d, slot)
    dup = Appointment(code="APT-X", patient_id=p.id, doctor_id=d.id, start_time=slot, end_time=slot + timedelta(minutes=30), status="scheduled", fee=0)
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_inactive_or_unavailable_doctor_rejected(app):
    p, d = make_patient(), make_doctor()
    slot = free_slot(d)
    d.accepting_appointments = False
    db.session.commit()
    with pytest.raises(BookingError, match="not available"):
        appointment_service.book_appointment(p, d, slot)
    d.accepting_appointments = True
    d.user.active = False
    db.session.commit()
    with pytest.raises(BookingError, match="not available"):
        appointment_service.book_appointment(p, d, slot)
    assert appointment_service.available_slots(d, slot.date()) == []


def test_past_and_off_schedule_times_rejected(app):
    p, d = make_patient(), make_doctor()
    with pytest.raises(BookingError, match="future"):
        appointment_service.book_appointment(p, d, hospital_now() - timedelta(hours=3))
    odd = free_slot(d) + timedelta(minutes=7)
    with pytest.raises(BookingError, match="working slots"):
        appointment_service.book_appointment(p, d, odd)


def test_booking_route_creates_pending_and_redirects_to_payment(app, login_as):
    p, d = make_patient(), make_doctor()
    c = login_as(p.user)
    slot = free_slot(d)
    resp = c.post("/appointments/book", data={"doctor_id": d.id, "slot": slot.strftime("%Y-%m-%dT%H:%M"),
                                                "status": "scheduled", "payment_status": "paid"})   # tampering ignored
    assert resp.status_code == 302 and "/payments/appointment/" in resp.headers["Location"]
    appt = Appointment.query.one()
    assert appt.status == "pending" and appt.payment_status == "pending"


def test_unpaid_hold_expires_and_frees_slot(app):
    p, d = make_patient(), make_doctor()
    slot = free_slot(d)
    appt = appointment_service.book_appointment(p, d, slot)
    appt.created_at = hospital_now() - timedelta(minutes=45)
    db.session.commit()
    assert slot in appointment_service.available_slots(d, slot.date())
    assert db.session.get(Appointment, appt.id).status == "cancelled"


def test_cancellation_policy_and_refund(app):
    p, d = make_patient(), make_doctor()
    appt = paid_appointment(p, d)                     # slot is >= 1 day ahead
    refund = appointment_service.cancel_appointment(appt)
    assert appt.status == "cancelled" and refund in (appt.fee, appt.fee / 2)
    near = paid_appointment(p, d, skip=3)
    near.start_time = hospital_now() + timedelta(hours=1)
    db.session.commit()
    with pytest.raises(BookingError, match="within 2 hours"):
        appointment_service.cancel_appointment(near)
    half = paid_appointment(p, d, skip=5)
    half.start_time = hospital_now() + timedelta(hours=5)
    db.session.commit()
    assert appointment_service.cancel_appointment(half) == half.fee / 2


def test_cannot_complete_before_consultation_recorded(app):
    p, d = make_patient(), make_doctor()
    appt = paid_appointment(p, d)
    with pytest.raises(BookingError, match="Record the consultation"):
        appointment_service.complete_appointment(appt)
    appointment_service.record_consultation(appt, "Dx (demo)", "Notes")
    appointment_service.complete_appointment(appt)
    assert appt.status == "completed"


def test_patient_cannot_cancel_someone_elses_appointment(app, login_as):
    p1, p2, d = make_patient(), make_patient(), make_doctor()
    appt = paid_appointment(p1, d)
    assert login_as(p2.user).post(f"/appointments/{appt.id}/cancel").status_code == 403
    assert db.session.get(Appointment, appt.id).status == "scheduled"
