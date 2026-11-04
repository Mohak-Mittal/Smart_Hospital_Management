"""Booking, cancelling and completing appointments."""
from datetime import datetime, timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment
from app.models.activity import log_activity
from app.models.appointment import SLOT_BLOCKING
from app.models.types import to_money
from app.utils.id_generator import finalize_code, temp_code
from app.utils.timeutil import hospital_now


class BookingError(Exception):
    """Raised with a user-friendly message when a booking rule is broken."""


def expire_stale_holds():
    """Unpaid 'pending' bookings free their slot after SLOT_HOLD_MINUTES."""
    cutoff = hospital_now() - timedelta(minutes=current_app.config["SLOT_HOLD_MINUTES"])
    stale = Appointment.query.filter(Appointment.status == "pending",
                                     Appointment.created_at < cutoff).all()
    for appt in stale:
        appt.status = "cancelled"
        appt.cancel_reason = "Payment window expired"
        appt.cancelled_at = hospital_now()
    if stale:
        db.session.commit()


def generate_slots(doctor, day):
    """All slot start times of `doctor` on `day` according to the weekly schedule."""
    if day.weekday() not in doctor.working_day_numbers:
        return []
    step = timedelta(minutes=doctor.slot_minutes)
    cursor = datetime.combine(day, doctor.start_time)
    end = datetime.combine(day, doctor.end_time)
    slots = []
    while cursor + step <= end:
        slots.append(cursor)
        cursor += step
    return slots


def _taken_starts(doctor, day):
    start = datetime.combine(day, datetime.min.time())
    rows = Appointment.query.filter(
        Appointment.doctor_id == doctor.id, Appointment.status.in_(SLOT_BLOCKING),
        Appointment.start_time >= start, Appointment.start_time < start + timedelta(days=1)).all()
    return {a.start_time for a in rows}


def available_slots(doctor, day):
    """Future, unbooked slots.  Inactive/unavailable doctors have none."""
    if not doctor.is_bookable:
        return []
    expire_stale_holds()
    now = hospital_now()
    taken = _taken_starts(doctor, day)
    return [s for s in generate_slots(doctor, day) if s > now and s not in taken]


def bookable_days(doctor, count=None):
    """Upcoming dates (within the booking window) that still have free slots."""
    count = count or current_app.config["BOOKING_WINDOW_DAYS"]
    today = hospital_now().date()
    return [today + timedelta(days=i) for i in range(count + 1)
            if available_slots(doctor, today + timedelta(days=i))]


def book_appointment(patient, doctor, start: datetime, reason: str = "") -> Appointment:
    """Create a PENDING appointment (slot held until payment succeeds).

    Rules: doctor bookable, slot on schedule, in the future, inside the booking
    window and not already taken.  The unique DB index is the final guard when
    two people click at the same time.
    """
    expire_stale_holds()
    now = hospital_now()
    if doctor is None or not doctor.is_bookable:
        raise BookingError("This doctor is not available for appointments.")
    if start <= now:
        raise BookingError("Please choose a time in the future.")
    if start > now + timedelta(days=current_app.config["BOOKING_WINDOW_DAYS"]):
        raise BookingError("That date is too far ahead to book.")
    if start not in generate_slots(doctor, start.date()):
        raise BookingError("That time is not one of the doctor's working slots.")
    if start in _taken_starts(doctor, start.date()):
        raise BookingError("Sorry, that slot has just been booked. Please pick another.")

    appt = Appointment(
        code=temp_code(), patient_id=patient.id, doctor_id=doctor.id, start_time=start,
        end_time=start + timedelta(minutes=doctor.slot_minutes), status="pending",
        payment_status="pending", fee=doctor.calculate_consultation_fee(),
        reason=(reason or "").strip()[:255] or None)
    try:
        db.session.add(appt)
        finalize_code(appt, "APT")
        log_activity(f"Appointment {appt.code} reserved for {patient.patient_code}", patient.user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BookingError("Sorry, that slot has just been booked. Please pick another.")
    return appt


def cancel_appointment(appt: Appointment, by_admin: bool = False, reason: str = "") -> Decimal:
    """Cancel + simulate refund.  Returns the refund amount.

    Policy (patients): not allowed within CANCEL_CUTOFF_HOURS of the start time.
    Refund: 100% if >= FULL_REFUND_HOURS ahead, otherwise 50%.  Admin cancellations refund 100%.
    """
    if appt.status not in ("pending", "scheduled"):
        raise BookingError("Only pending or scheduled appointments can be cancelled.")
    now = hospital_now()
    hours = (appt.start_time - now).total_seconds() / 3600
    cfg = current_app.config
    if not by_admin and hours < cfg["CANCEL_CUTOFF_HOURS"]:
        raise BookingError(f"Appointments cannot be cancelled within {cfg['CANCEL_CUTOFF_HOURS']} hours of the start time.")
    refund = Decimal("0.00")
    if appt.payment_status == "paid":
        pct = Decimal("1") if (by_admin or hours >= cfg["FULL_REFUND_HOURS"]) else Decimal("0.5")
        refund = to_money(appt.fee * pct)
        appt.payment_status = "refunded" if pct == 1 else "partially_refunded"
    appt.refund_amount = refund
    appt.status = "cancelled"
    appt.cancelled_at = now
    appt.cancel_reason = (reason or "Cancelled by " + ("admin" if by_admin else "patient"))[:255]
    log_activity(f"Appointment {appt.code} cancelled", None)
    db.session.commit()
    return refund


def record_consultation(appt: Appointment, diagnosis: str, notes: str):
    if appt.status not in ("scheduled", "emergency"):
        raise BookingError("Consultation can only be recorded for scheduled or emergency appointments.")
    diagnosis, notes = (diagnosis or "").strip(), (notes or "").strip()
    if not diagnosis or not notes:
        raise BookingError("Diagnosis and consultation notes are both required.")
    appt.diagnosis, appt.consultation_notes = diagnosis, notes
    appt.consultation_recorded_at = hospital_now()
    db.session.commit()


def complete_appointment(appt: Appointment):
    """Allowed only after the consultation workflow has been recorded."""
    if appt.status not in ("scheduled", "emergency"):
        raise BookingError("Only scheduled or emergency appointments can be completed.")
    if appt.consultation_recorded_at is None:
        raise BookingError("Record the consultation (diagnosis and notes) before completing.")
    appt.status = "completed"
    log_activity(f"Appointment {appt.code} completed", None)
    db.session.commit()
