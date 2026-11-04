"""Booking + cancelling (patient actions)."""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import Appointment, Doctor
from app.services import appointment_service
from app.services.appointment_service import BookingError
from app.utils.decorators import role_required

appointments_bp = Blueprint("appointments", __name__)


def _own_appointment(appt_id):
    appt = db.get_or_404(Appointment, appt_id)
    patient = current_user.patient_profile
    if patient is None or appt.patient_id != patient.id:
        abort(403)
    return appt


@appointments_bp.route("/book", methods=["POST"])
@role_required("patient")
def book():
    patient = current_user.patient_profile
    doctor = db.session.get(Doctor, request.form.get("doctor_id", type=int) or 0)
    try:
        start = datetime.strptime(request.form.get("slot", ""), "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Please choose a valid time slot.", "danger")
        return redirect(request.referrer or url_for("patient.doctors"))
    try:
        # Only doctor, time and reason are read from the form. Status, fee and payment
        # status are decided by the server so a patient cannot tamper with them.
        appt = appointment_service.book_appointment(patient, doctor, start, request.form.get("reason", ""))
    except BookingError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("patient.doctor_detail", doctor_id=doctor.id) if doctor else url_for("patient.doctors"))
    flash("Slot reserved. Complete the demo payment to confirm your booking.", "info")
    return redirect(url_for("payments.pay_appointment", appt_id=appt.id))


@appointments_bp.route("/<int:appt_id>/cancel", methods=["POST"])
@role_required("patient")
def cancel(appt_id):
    appt = _own_appointment(appt_id)
    try:
        refund = appointment_service.cancel_appointment(appt)
        flash("Appointment cancelled." + (f" Demo refund of ₹{refund:,.2f} issued." if refund else ""), "success")
    except BookingError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("patient.appointments", tab="all"))
