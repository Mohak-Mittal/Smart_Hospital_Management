"""Central place for 'who may see which patient / document' rules.

Routes call these helpers on EVERY request - hiding a button is not security.
"""
from app.models import Appointment, Bill, MedicalReport, TreatmentPlan


def doctor_can_access_patient(doctor, patient) -> bool:
    """A doctor may open a patient only if linked by a confirmed appointment or a treatment."""
    if doctor is None or patient is None:
        return False
    has_appt = (Appointment.query.filter(
        Appointment.doctor_id == doctor.id, Appointment.patient_id == patient.id,
        Appointment.status.in_(("scheduled", "completed", "emergency"))).first() is not None)
    if has_appt:
        return True
    return TreatmentPlan.query.filter_by(doctor_id=doctor.id, patient_id=patient.id).first() is not None


def nurse_can_access_patient(nurse, patient) -> bool:
    return bool(nurse and patient and patient in nurse.assigned_patients)


def user_can_view_bill(user, bill: Bill) -> bool:
    if user.role == "admin":
        return True
    return user.role == "patient" and user.patient_profile is not None \
        and bill.patient_id == user.patient_profile.id


def user_can_view_report(user, report: MedicalReport) -> bool:
    if user.role == "admin":
        return True
    if user.role == "patient":
        p = user.patient_profile
        return bool(p and report.patient_id == p.id and report.is_published)
    if user.role == "doctor":
        d = user.doctor_profile
        return bool(d and report.doctor_id == d.id)   # only the author doctor
    return False
