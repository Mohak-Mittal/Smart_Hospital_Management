"""Treatments.

* `Treatment` (ABC) and its subclasses = the business behaviour
  (ABSTRACTION + POLYMORPHISM: each type overrides perform_treatment and
  calculate_cost).
* `TreatmentPlan` (ORM) = the saved database row.  It stores the type + numbers
  and builds the right Treatment object through `as_treatment()` (a factory
  registry instead of a big if/elif).
"""
from abc import ABC, abstractmethod
from decimal import Decimal

from app.extensions import db
from app.models.types import to_money
from app.utils.timeutil import hospital_now

TREATMENT_STATUSES = ("planned", "in_progress", "completed", "cancelled")


class Treatment(ABC):
    type_key = ""
    label = ""
    required = ()          # parameter names that must be > 0

    def __init__(self, **params):
        self.params = {k: to_money(v) for k, v in params.items() if k != "sessions"}
        self.sessions = int(params.get("sessions") or 0)

    @classmethod
    def validate(cls, params: dict):
        for key, value in params.items():
            if key != "sessions" and to_money(value) < 0:
                raise ValueError(f"{key.replace('_', ' ').title()} cannot be negative.")
        for key in cls.required:
            if key == "sessions":
                if int(params.get(key) or 0) <= 0:
                    raise ValueError("Number of sessions must be at least 1.")
            elif to_money(params.get(key)) <= 0:
                raise ValueError(f"{key.replace('_', ' ').title()} must be greater than 0.")

    def _p(self, key) -> Decimal:
        return self.params.get(key, Decimal("0.00"))

    @abstractmethod
    def perform_treatment(self) -> str:
        """Describe what is done (demo text)."""

    @abstractmethod
    def calculate_cost(self) -> Decimal:
        """Total charge for this treatment."""

    def __str__(self):
        return f"{self.label} (₹{self.calculate_cost():,.2f})"


class MedicineTreatment(Treatment):
    type_key, label = "medicine", "Medicine treatment"
    required = ("medicine_charges",)

    def perform_treatment(self):
        return "Prescribed medicines are given and the response is monitored."

    def calculate_cost(self):  # medicine charges + consultation charges
        return to_money(self._p("medicine_charges") + self._p("consultation_charges"))


class SurgeryTreatment(Treatment):
    type_key, label = "surgery", "Surgery"
    required = ("operation_charges", "surgeon_charges")

    def perform_treatment(self):
        return "Surgical procedure is performed in the operation theatre."

    def calculate_cost(self):  # operation + surgeon + hospital charges
        return to_money(self._p("operation_charges") + self._p("surgeon_charges")
                        + self._p("hospital_charges"))


class PhysiotherapyTreatment(Treatment):
    type_key, label = "physiotherapy", "Physiotherapy"
    required = ("session_charges", "sessions")

    def perform_treatment(self):
        return f"{self.sessions} physiotherapy session(s) are scheduled."

    def calculate_cost(self):  # session charge x number of sessions
        return to_money(self._p("session_charges") * self.sessions)


class EmergencyTreatment(Treatment):
    type_key, label = "emergency", "Emergency treatment"
    required = ("emergency_charges",)

    def perform_treatment(self):
        return "Immediate stabilising care is provided in the emergency unit."

    def calculate_cost(self):  # emergency charges + treatment charges
        return to_money(self._p("emergency_charges") + self._p("treatment_charges"))


TREATMENT_REGISTRY = {c.type_key: c for c in
                      (MedicineTreatment, SurgeryTreatment, PhysiotherapyTreatment, EmergencyTreatment)}
TREATMENT_CHOICES = [(k, c.label) for k, c in TREATMENT_REGISTRY.items()]
PARAM_KEYS = ("medicine_charges", "consultation_charges", "operation_charges", "surgeon_charges",
              "hospital_charges", "session_charges", "sessions", "emergency_charges",
              "treatment_charges")


class TreatmentPlan(db.Model):
    __tablename__ = "treatment_plans"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"))
    treatment_type = db.Column(db.String(20), nullable=False)
    diagnosis = db.Column(db.String(255))
    plan_details = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="planned")
    params = db.Column(db.JSON, nullable=False, default=dict)   # numbers stored as strings
    doctor_approved_at = db.Column(db.DateTime)                 # doctor approval for discharge
    discharged_at = db.Column(db.DateTime)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"))
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=hospital_now)

    patient = db.relationship("Patient", backref=db.backref("treatments", lazy="dynamic"))
    doctor = db.relationship("Doctor", backref=db.backref("treatments", lazy="dynamic"))
    progress = db.relationship("TreatmentProgress", backref="treatment",
                               order_by="TreatmentProgress.created_at.desc()",
                               cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("status IN ('planned','in_progress','completed','cancelled')",
                           name="ck_treatment_status"),
    )

    def as_treatment(self) -> Treatment:
        cls = TREATMENT_REGISTRY[self.treatment_type]
        return cls(**(self.params or {}))

    @property
    def type_label(self):
        return TREATMENT_REGISTRY[self.treatment_type].label

    @property
    def cost(self) -> Decimal:
        return self.as_treatment().calculate_cost()

    @property
    def is_open(self):
        return self.status in ("planned", "in_progress")

    def __str__(self):
        return f"{self.code} - {self.type_label} ({self.status})"


class TreatmentProgress(db.Model):
    """Progress notes, medication entries and nursing notes (timeline items)."""
    __tablename__ = "treatment_progress"

    id = db.Column(db.Integer, primary_key=True)
    treatment_id = db.Column(db.Integer, db.ForeignKey("treatment_plans.id"), nullable=False, index=True)
    author_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    kind = db.Column(db.String(20), nullable=False, default="progress")  # progress|medication|nursing|status
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=hospital_now)

    author = db.relationship("User")
