"""Nurse portal: limited to assigned patients; can read treatment status and add nursing notes."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import ProgressForm
from app.models import Patient, RoomAssignment, TreatmentPlan
from app.services import treatment_service
from app.services.access import nurse_can_access_patient
from app.services.treatment_service import TreatmentError
from app.utils.decorators import role_required

nurse_bp = Blueprint("nurse", __name__)


def me():
    nurse = current_user.nurse_profile
    if nurse is None:
        abort(403)
    return nurse


@nurse_bp.route("/")
@role_required("nurse")
def dashboard():
    n = me()
    rows = []
    for p in n.assigned_patients:
        plan = p.treatments.filter(TreatmentPlan.discharged_at.is_(None), TreatmentPlan.status != "cancelled") \
            .order_by(TreatmentPlan.created_at.desc()).first()
        stay = RoomAssignment.query.filter_by(patient_id=p.id, released_at=None).first()
        rows.append((p, plan, stay))
    return render_template("nurse/dashboard.html", nurse=n, rows=rows)


@nurse_bp.route("/patients/<int:patient_id>")
@role_required("nurse")
def patient_detail(patient_id):
    n = me()
    patient = db.get_or_404(Patient, patient_id)
    if not nurse_can_access_patient(n, patient):
        abort(403)
    plans = patient.treatments.order_by(TreatmentPlan.created_at.desc()).all()
    stay = RoomAssignment.query.filter_by(patient_id=patient.id, released_at=None).first()
    return render_template("nurse/patient_detail.html", patient=patient, plans=plans, stay=stay,
                           form=ProgressForm(prefix="n", meta={"csrf": False}))


@nurse_bp.route("/treatments/<int:plan_id>/note", methods=["POST"])
@role_required("nurse")
def add_note(plan_id):
    n = me()
    plan = db.get_or_404(TreatmentPlan, plan_id)
    if not nurse_can_access_patient(n, plan.patient):
        abort(403)
    note = request.form.get("n-note", "")
    if len(note) > 2000:
        flash("Note is too long (max 2000 characters).", "danger")
    else:
        try:
            treatment_service.add_progress(plan, current_user, "nursing", note)
            flash("Nursing note added.", "success")
        except TreatmentError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("nurse.patient_detail", patient_id=plan.patient_id))
