"""Treatment plans: create, move through statuses, add notes, approve discharge."""
from app.extensions import db
from app.models import TreatmentPlan, TreatmentProgress
from app.models.activity import log_activity
from app.models.treatment import PARAM_KEYS, TREATMENT_REGISTRY
from app.utils.id_generator import finalize_code, temp_code
from app.utils.timeutil import hospital_now

ALLOWED = {"planned": ("in_progress", "cancelled"),
           "in_progress": ("completed", "cancelled"),
           "completed": (), "cancelled": ()}


class TreatmentError(Exception):
    pass


def add_progress(plan, user, kind, note, commit=True):
    note = (note or "").strip()
    if not note:
        raise TreatmentError("Please write a note.")
    if kind not in ("progress", "medication", "nursing", "status"):
        raise TreatmentError("Unknown note type.")
    db.session.add(TreatmentProgress(treatment_id=plan.id, author_user_id=user.id, kind=kind, note=note))
    if commit:
        db.session.commit()


def create_plan(doctor, patient, treatment_type, diagnosis, details, params, appointment=None):
    cls = TREATMENT_REGISTRY.get(treatment_type)
    if cls is None:
        raise TreatmentError("Choose a valid treatment type.")
    clean = {k: str(params.get(k) or 0) for k in PARAM_KEYS}
    try:
        cls.validate(clean)
    except ValueError as exc:
        raise TreatmentError(str(exc))
    if not (diagnosis or "").strip():
        raise TreatmentError("Diagnosis is required.")
    plan = TreatmentPlan(code=temp_code(), patient_id=patient.id, doctor_id=doctor.id,
                         appointment_id=appointment.id if appointment else None,
                         treatment_type=treatment_type, diagnosis=diagnosis.strip()[:255],
                         plan_details=(details or "").strip(), params=clean, status="planned")
    db.session.add(plan)
    finalize_code(plan, "TRT", "code")
    log_activity(f"Treatment plan {plan.code} created for {patient.patient_code}", doctor.user)
    db.session.commit()
    return plan


def set_status(plan, new_status, user):
    if new_status not in ALLOWED.get(plan.status, ()):
        raise TreatmentError(f"Cannot change status from {plan.status} to {new_status}.")
    plan.status = new_status
    now = hospital_now()
    if new_status == "in_progress":
        plan.started_at = now
    if new_status == "completed":
        plan.completed_at = now
    add_progress(plan, user, "status", f"Status changed to {new_status.replace('_', ' ')}.", commit=False)
    db.session.commit()


def approve_discharge(plan, user):
    if plan.status != "completed":
        raise TreatmentError("Complete the treatment before approving discharge.")
    if plan.doctor_approved_at:
        raise TreatmentError("Discharge is already approved for this treatment.")
    plan.doctor_approved_at = hospital_now()
    add_progress(plan, user, "status", "Doctor approved discharge.", commit=False)
    log_activity(f"Discharge approved on {plan.code}", user)
    db.session.commit()
