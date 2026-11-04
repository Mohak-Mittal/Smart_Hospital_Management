"""Patient portal.  Every query is filtered by the logged-in patient's id."""
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from app.extensions import db
from app.forms import PatientProfileForm
from app.models import Appointment, Bill, Doctor, MedicalReport, RoomAssignment, Specialization, TreatmentPlan, User
from app.models.activity import log_activity
from app.models.types import to_money
from app.routes import paginate
from app.services import appointment_service, billing_service
from app.services.access import user_can_view_report
from app.utils.decorators import role_required
from app.utils.timeutil import hospital_now

patient_bp = Blueprint("patient", __name__)


def me():
    patient = current_user.patient_profile
    if patient is None:
        abort(403)
    return patient


@patient_bp.route("/")
@role_required("patient")
def dashboard():
    p, now = me(), hospital_now()
    appointment_service.expire_stale_holds()
    upcoming = (p.appointments.filter(Appointment.status == "scheduled", Appointment.start_time >= now)
                .order_by(Appointment.start_time).limit(5).all())
    pending = p.appointments.filter(Appointment.status == "pending").count()
    plan = p.treatments.filter(TreatmentPlan.status.in_(("planned", "in_progress"))).order_by(TreatmentPlan.created_at.desc()).first()
    return render_template("patient/dashboard.html", patient=p, upcoming=upcoming, pending=pending, plan=plan,
                           outstanding=billing_service.outstanding_for_patient(p),
                           report_count=sum(1 for r in p.reports if r.is_published),
                           policy=p.active_policy)


@patient_bp.route("/doctors")
@role_required("patient")
def doctors():
    me()
    q = request.args.get("q", "").strip()
    spec = request.args.get("specialization", type=int)
    dept = request.args.get("department", "").strip()
    max_fee = request.args.get("max_fee", "").strip()
    fee_expr = func.coalesce(Doctor.fee_override, Specialization.base_fee)
    query = (Doctor.query.join(User, Doctor.user_id == User.id)
             .join(Specialization, Doctor.specialization_id == Specialization.id).filter(User.active.is_(True)))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), Specialization.name.ilike(like), Doctor.department.ilike(like)))
    if spec:
        query = query.filter(Doctor.specialization_id == spec)
    if dept:
        query = query.filter(Doctor.department.ilike(f"%{dept}%"))
    if max_fee:
        try:
            query = query.filter(fee_expr <= to_money(max_fee))
        except Exception:
            flash("Maximum fee must be a number.", "warning")
    page = paginate(query.order_by(User.name))
    return render_template("patient/doctors.html", page=page, specs=Specialization.query.order_by(Specialization.name).all(),
                           q=q, spec=spec, dept=dept, max_fee=max_fee)


@patient_bp.route("/doctors/<int:doctor_id>")
@role_required("patient")
def doctor_detail(doctor_id):
    me()
    doctor = db.get_or_404(Doctor, doctor_id)
    today = hospital_now().date()
    days = appointment_service.bookable_days(doctor, 14)
    chosen = today
    raw = request.args.get("date")
    if raw:
        try:
            chosen = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            flash("That date is not valid.", "warning")
    elif days:
        chosen = days[0]
    slots = appointment_service.available_slots(doctor, chosen) if today <= chosen <= today + timedelta(days=30) else []
    return render_template("patient/doctor_detail.html", doctor=doctor, days=days, chosen=chosen, slots=slots)


@patient_bp.route("/appointments")
@role_required("patient")
def appointments():
    p, now = me(), hospital_now()
    appointment_service.expire_stale_holds()
    tab = request.args.get("tab", "upcoming")
    query = p.appointments
    if tab == "upcoming":
        query = query.filter(Appointment.status.in_(("scheduled", "emergency")), Appointment.start_time >= now)
    elif tab in ("pending", "completed", "cancelled"):
        query = query.filter(Appointment.status == tab)
    else:
        tab = "all"
    page = paginate(query.order_by(Appointment.start_time.desc() if tab != "upcoming" else Appointment.start_time))
    return render_template("patient/appointments.html", page=page, tab=tab, now=now)


@patient_bp.route("/treatment")
@role_required("patient")
def treatment_status():
    p = me()
    plans = p.treatments.order_by(TreatmentPlan.created_at.desc()).all()
    stays = p.room_assignments.order_by(RoomAssignment.assigned_at.desc()).all()
    return render_template("patient/treatment_status.html", plans=plans, stays=stays, discharges=p.discharges.all())


@patient_bp.route("/reports")
@role_required("patient")
def reports():
    p = me()
    page = paginate(MedicalReport.query.filter_by(patient_id=p.id, status="published")
                    .order_by(MedicalReport.published_at.desc()))
    return render_template("patient/reports.html", page=page)


@patient_bp.route("/reports/<int:report_id>")
@role_required("patient")
def report_detail(report_id):
    report = db.get_or_404(MedicalReport, report_id)
    if not user_can_view_report(current_user, report):
        abort(403)
    return render_template("patient/report_detail.html", report=report)


@patient_bp.route("/invoices")
@role_required("patient")
def invoices():
    p = me()
    bills = paginate(p.bills.order_by(Bill.created_at.desc()))
    payments = p.payments.order_by(db.text("created_at DESC")).limit(30).all()
    return render_template("patient/invoices.html", page=bills, payments=payments, policy=p.active_policy,
                           outstanding=billing_service.outstanding_for_patient(p))


@patient_bp.route("/profile", methods=["GET", "POST"])
@role_required("patient")
def profile():
    p = me()
    form = PatientProfileForm(obj=p)
    if request.method == "GET":
        form.medical_history.data = p.medical_history
    if form.validate_on_submit():
        p.phone = form.phone.data or None
        p.date_of_birth = form.date_of_birth.data
        p.gender = form.gender.data or None
        p.blood_group = form.blood_group.data or None
        p.address = form.address.data or None
        p.emergency_contact = form.emergency_contact.data or None
        p.medical_history = form.medical_history.data
        log_activity(f"Profile updated ({p.patient_code})", current_user)
        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("patient.profile"))
    return render_template("patient/profile.html", form=form, patient=p)
