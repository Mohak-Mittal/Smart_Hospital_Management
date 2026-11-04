"""Doctor portal.  A doctor can only open patients linked to them (see services/access.py)."""
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import ConsultationForm, ProgressForm, ReportForm, TreatmentForm
from app.models import Appointment, MedicalReport, Patient, TreatmentPlan
from app.models.activity import log_activity
from app.models.treatment import PARAM_KEYS
from app.routes import flash_form_errors, paginate
from app.services import appointment_service, treatment_service
from app.services.access import doctor_can_access_patient
from app.services.appointment_service import BookingError
from app.services.treatment_service import TreatmentError
from app.utils.decorators import role_required
from app.utils.id_generator import finalize_code, temp_code
from app.utils.timeutil import hospital_now

doctor_bp = Blueprint("doctor", __name__)


def me():
    doctor = current_user.doctor_profile
    if doctor is None:
        abort(403)
    return doctor


def patient_for(doctor, patient_id):
    patient = db.get_or_404(Patient, patient_id)
    if not doctor_can_access_patient(doctor, patient):
        abort(403)
    return patient


def own_appointment(doctor, appt_id):
    appt = db.get_or_404(Appointment, appt_id)
    if appt.doctor_id != doctor.id:
        abort(403)
    return appt


def own_treatment(doctor, plan_id):
    plan = db.get_or_404(TreatmentPlan, plan_id)
    if plan.doctor_id != doctor.id:
        abort(403)
    return plan


@doctor_bp.route("/")
@role_required("doctor")
def dashboard():
    d, now = me(), hospital_now()
    start = datetime.combine(now.date(), datetime.min.time())
    live = ("scheduled", "completed", "emergency")
    today = (d.appointments.filter(Appointment.status.in_(live), Appointment.start_time >= start,
                                   Appointment.start_time < start + timedelta(days=1))
             .order_by(Appointment.start_time).all())
    upcoming = (d.appointments.filter(Appointment.status == "scheduled",
                                      Appointment.start_time >= start + timedelta(days=1))
                .order_by(Appointment.start_time).limit(8).all())
    drafts = d.reports.filter_by(status="draft").count()
    open_plans = d.treatments.filter(TreatmentPlan.status.in_(("planned", "in_progress"))).count()
    return render_template("doctor/dashboard.html", doctor=d, today=today, upcoming=upcoming, drafts=drafts,
                           open_plans=open_plans, now=now)


@doctor_bp.route("/appointments")
@role_required("doctor")
def appointments():
    d = me()
    status = request.args.get("status", "")
    day = request.args.get("date", "")
    query = d.appointments.filter(Appointment.status != "pending")
    if status in ("scheduled", "completed", "cancelled", "emergency"):
        query = query.filter(Appointment.status == status)
    if day:
        try:
            s = datetime.strptime(day, "%Y-%m-%d")
            query = query.filter(Appointment.start_time >= s, Appointment.start_time < s + timedelta(days=1))
        except ValueError:
            flash("Invalid date filter.", "warning")
    page = paginate(query.order_by(Appointment.start_time.desc()))
    return render_template("doctor/appointments.html", page=page, status=status, day=day)


def _detail(doctor, patient, **forms):
    appts = patient.appointments.filter(Appointment.doctor_id == doctor.id,
                                        Appointment.status != "pending").order_by(Appointment.start_time.desc()).all()
    plans = patient.treatments.filter(TreatmentPlan.doctor_id == doctor.id).order_by(TreatmentPlan.created_at.desc()).all()
    reports = [r for r in patient.reports if r.doctor_id == doctor.id]
    return render_template(
        "doctor/patient_detail.html", doctor=doctor, patient=patient, appts=appts, plans=plans, reports=reports,
        consult_form=forms.get("consult_form") or ConsultationForm(prefix="c", meta={"csrf": False}),
        consult_appt_id=forms.get("consult_appt_id"),
        treatment_form=forms.get("treatment_form") or TreatmentForm(prefix="t", meta={"csrf": False}),
        report_form=forms.get("report_form") or ReportForm(prefix="r", meta={"csrf": False}),
        progress_form=ProgressForm(prefix="p", meta={"csrf": False}))


@doctor_bp.route("/patients/<int:patient_id>")
@role_required("doctor")
def patient_detail(patient_id):
    d = me()
    return _detail(d, patient_for(d, patient_id))


@doctor_bp.route("/appointments/<int:appt_id>/consultation", methods=["POST"])
@role_required("doctor")
def consultation(appt_id):
    d = me()
    appt = own_appointment(d, appt_id)
    patient = patient_for(d, appt.patient_id)
    form = ConsultationForm(prefix="c", meta={"csrf": False})
    if form.validate_on_submit():
        try:
            appointment_service.record_consultation(appt, form.diagnosis.data, form.notes.data)
            flash("Consultation recorded.", "success")
            return redirect(url_for("doctor.patient_detail", patient_id=patient.id))
        except BookingError as exc:
            flash(str(exc), "danger")
    return _detail(d, patient, consult_form=form, consult_appt_id=appt.id)


@doctor_bp.route("/appointments/<int:appt_id>/complete", methods=["POST"])
@role_required("doctor")
def complete(appt_id):
    d = me()
    appt = own_appointment(d, appt_id)
    try:
        appointment_service.complete_appointment(appt)
        flash("Appointment marked completed.", "success")
    except BookingError as exc:
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("doctor.patient_detail", patient_id=appt.patient_id))


@doctor_bp.route("/patients/<int:patient_id>/treatments", methods=["POST"])
@role_required("doctor")
def create_treatment(patient_id):
    d = me()
    patient = patient_for(d, patient_id)
    form = TreatmentForm(prefix="t", meta={"csrf": False})
    if form.validate_on_submit():
        params = {k: getattr(form, k).data for k in PARAM_KEYS}
        try:
            plan = treatment_service.create_plan(d, patient, form.treatment_type.data, form.diagnosis.data,
                                                 form.plan_details.data, params)
            flash(f"Treatment plan {plan.code} created.", "success")
            return redirect(url_for("doctor.patient_detail", patient_id=patient.id))
        except TreatmentError as exc:
            form.treatment_type.errors = list(form.treatment_type.errors) + [str(exc)]
    return _detail(d, patient, treatment_form=form)


@doctor_bp.route("/treatments/<int:plan_id>/status", methods=["POST"])
@role_required("doctor")
def treatment_status(plan_id):
    d = me()
    plan = own_treatment(d, plan_id)
    try:
        treatment_service.set_status(plan, request.form.get("status", ""), current_user)
        flash("Treatment status updated.", "success")
    except TreatmentError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("doctor.patient_detail", patient_id=plan.patient_id))


@doctor_bp.route("/treatments/<int:plan_id>/progress", methods=["POST"])
@role_required("doctor")
def treatment_progress(plan_id):
    d = me()
    plan = own_treatment(d, plan_id)
    form = ProgressForm(prefix="p", meta={"csrf": False})
    if form.validate_on_submit():
        try:
            treatment_service.add_progress(plan, current_user, form.kind.data, form.note.data)
            flash("Entry added to the timeline.", "success")
        except TreatmentError as exc:
            flash(str(exc), "danger")
    else:
        flash_form_errors(form)
    return redirect(url_for("doctor.patient_detail", patient_id=plan.patient_id))


@doctor_bp.route("/treatments/<int:plan_id>/approve-discharge", methods=["POST"])
@role_required("doctor")
def approve_discharge(plan_id):
    d = me()
    plan = own_treatment(d, plan_id)
    try:
        treatment_service.approve_discharge(plan, current_user)
        flash("Discharge approval recorded.", "success")
    except TreatmentError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("doctor.patient_detail", patient_id=plan.patient_id))


@doctor_bp.route("/patients/<int:patient_id>/reports", methods=["POST"])
@role_required("doctor")
def create_report(patient_id):
    d = me()
    patient = patient_for(d, patient_id)
    form = ReportForm(prefix="r", meta={"csrf": False})
    if form.validate_on_submit():
        report = MedicalReport(report_code=temp_code(), patient_id=patient.id, doctor_id=d.id,
                               title=form.title.data.strip(), content=form.content.data.strip(), status="draft")
        db.session.add(report)
        finalize_code(report, "REP", "report_code")
        db.session.commit()
        flash("Draft saved. Publish it when it is ready for the patient.", "success")
        return redirect(url_for("doctor.patient_detail", patient_id=patient.id))
    return _detail(d, patient, report_form=form)


@doctor_bp.route("/reports")
@role_required("doctor")
def reports():
    d = me()
    page = paginate(d.reports.order_by(MedicalReport.created_at.desc()))
    return render_template("doctor/reports.html", page=page)


@doctor_bp.route("/reports/<int:report_id>/publish", methods=["POST"])
@role_required("doctor")
def publish_report(report_id):
    d = me()
    report = db.get_or_404(MedicalReport, report_id)
    if report.doctor_id != d.id:          # only the AUTHOR may publish - this is the doctor's authorization
        abort(403)
    if report.is_published:
        flash("This report is already published.", "info")
    else:
        report.status = "published"
        report.published_at = hospital_now()
        log_activity(f"Report {report.report_code} published", current_user)
        db.session.commit()
        flash("Report published to the patient portal.", "success")
    return redirect(request.referrer or url_for("doctor.reports"))
