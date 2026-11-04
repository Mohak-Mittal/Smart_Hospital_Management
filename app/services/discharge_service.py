"""Discharge rules.  A patient can leave only when ALL four conditions are met."""
from dataclasses import dataclass

from app.extensions import db
from app.models import Discharge, RoomAssignment, TreatmentPlan, Patient
from app.models.activity import log_activity
from app.services import room_service
from app.utils.timeutil import hospital_now


class DischargeError(Exception):
    def __init__(self, unmet):
        self.unmet = unmet
        super().__init__("Discharge not allowed: " + "; ".join(unmet))


@dataclass
class Condition:
    key: str
    label: str
    met: bool
    detail: str = ""


@dataclass
class DischargeCheck:
    conditions: list

    @property
    def eligible(self):
        return all(c.met for c in self.conditions)

    @property
    def unmet(self):
        return [f"{c.label} ({c.detail})" if c.detail else c.label for c in self.conditions if not c.met]


def _episode(patient):
    return TreatmentPlan.query.filter(
        TreatmentPlan.patient_id == patient.id, TreatmentPlan.discharged_at.is_(None),
        TreatmentPlan.status != "cancelled").all()


def evaluate(patient) -> DischargeCheck:
    plans = _episode(patient)
    stays = RoomAssignment.query.filter_by(patient_id=patient.id, released_at=None).all()
    bills = patient.bills.all()

    if not plans:
        open_detail = "no active treatment on record"
        treat_ok = approve_ok = billed_ok = False
        approve_detail = billed_detail = open_detail
    else:
        open_plans = [p.code for p in plans if p.status != "completed"]
        treat_ok = not open_plans
        open_detail = "not completed: " + ", ".join(open_plans) if open_plans else ""
        unapproved = [p.code for p in plans if p.doctor_approved_at is None]
        approve_ok = not unapproved
        approve_detail = "awaiting approval: " + ", ".join(unapproved) if unapproved else ""
        unbilled = [p.code for p in plans if p.bill_id is None] + \
                   [f"room {s.room.room_number}" for s in stays if s.bill_id is None]
        billed_ok = not unbilled
        billed_detail = "not billed yet: " + ", ".join(unbilled) if unbilled else ""

    owing = [f"{b.invoice_number} (₹{b.balance_due:,.2f})" for b in bills if b.balance_due > 0]
    unsettled = [b.invoice_number for b in bills if b.insurance_coverage > 0 and not b.insurer_settled]
    pay_ok = bool(bills) and not owing and not unsettled
    parts = []
    if not bills:
        parts.append("no bill exists")
    if owing:
        parts.append("balance due: " + ", ".join(owing))
    if unsettled:
        parts.append("insurer share not settled: " + ", ".join(unsettled))

    return DischargeCheck([
        Condition("treatment", "Treatment completed", treat_ok, open_detail),
        Condition("approval", "Doctor approval recorded", approve_ok, approve_detail),
        Condition("bill", "Bill generated", billed_ok, billed_detail),
        Condition("payment", "Payment completed", pay_ok, "; ".join(parts)),
    ])


def candidates():
    """Patients who currently have an open treatment episode or occupy a room."""
    ids = {p.patient_id for p in TreatmentPlan.query.filter(
        TreatmentPlan.discharged_at.is_(None), TreatmentPlan.status != "cancelled")}
    ids |= {s.patient_id for s in RoomAssignment.query.filter_by(released_at=None)}
    return Patient.query.filter(Patient.id.in_(ids)).order_by(Patient.id).all() if ids else []


def discharge_patient(patient, user, notes="") -> Discharge:
    check = evaluate(patient)
    if not check.eligible:
        raise DischargeError(check.unmet)
    now = hospital_now()
    released = []
    try:
        for plan in _episode(patient):
            plan.discharged_at = now
        for stay in RoomAssignment.query.filter_by(patient_id=patient.id, released_at=None).all():
            released.append(f"{stay.room.room_type.name} {stay.room.room_number}")
            room_service.release_assignment(stay, user, commit=False)
        record = Discharge(patient_id=patient.id, discharged_at=now, discharged_by_user_id=user.id,
                           room_released=", ".join(released) or None, notes=(notes or "")[:255] or None)
        db.session.add(record)
        log_activity(f"Patient {patient.patient_code} discharged", user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return record
