"""Doctor profile, specializations (POLYMORPHISM) and schedule."""
from abc import ABC, abstractmethod
from datetime import time
from decimal import Decimal

from app.extensions import db
from app.models.types import Money, to_money
from app.models.user import HospitalUser

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------- policies
class SpecializationPolicy(ABC):
    """ABSTRACTION: each medical specialization decides its own fee rules.

    The *base fee* is stored in the database (admins can change it); the policy
    class only holds the behaviour.  Subclasses OVERRIDE the methods below.
    """
    key = ""
    label = ""

    @abstractmethod
    def calculate_consultation_fee(self, base_fee, follow_up: bool = False) -> Decimal:
        ...

    def display_details(self) -> str:
        return f"{self.label} consultation"


class GeneralPhysicianPolicy(SpecializationPolicy):
    key, label = "general", "General Physician"

    def calculate_consultation_fee(self, base_fee, follow_up=False):
        fee = to_money(base_fee)
        return to_money(fee * Decimal("0.80")) if follow_up else fee  # 20% off follow-ups


class CardiologistPolicy(SpecializationPolicy):
    key, label = "cardiologist", "Cardiologist"

    def calculate_consultation_fee(self, base_fee, follow_up=False):
        fee = to_money(base_fee)
        return to_money(fee * Decimal("0.90")) if follow_up else fee  # 10% off follow-ups

    def display_details(self):
        return "Cardiologist consultation (heart & circulation)"


class NeurologistPolicy(SpecializationPolicy):
    key, label = "neurologist", "Neurologist"

    def calculate_consultation_fee(self, base_fee, follow_up=False):
        fee = to_money(base_fee)
        return to_money(fee * Decimal("0.90")) if follow_up else fee

    def display_details(self):
        return "Neurologist consultation (brain & nerves)"


class SurgeonPolicy(SpecializationPolicy):
    key, label = "surgeon", "Surgeon"

    def calculate_consultation_fee(self, base_fee, follow_up=False):
        return to_money(base_fee)  # surgeons: no follow-up discount

    def display_details(self):
        return "Surgeon consultation (pre-operative assessment)"


POLICY_REGISTRY = {p.key: p for p in
                   (GeneralPhysicianPolicy(), CardiologistPolicy(), NeurologistPolicy(), SurgeonPolicy())}


def get_policy(key: str) -> SpecializationPolicy:
    """Registry lookup instead of a giant if/elif chain."""
    return POLICY_REGISTRY.get(key, POLICY_REGISTRY["general"])


class Specialization(db.Model):
    __tablename__ = "specializations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    policy_key = db.Column(db.String(30), nullable=False, default="general")
    base_fee = db.Column(Money, nullable=False, default=Decimal("500.00"))
    description = db.Column(db.String(255))

    def __str__(self):
        return self.name


class Doctor(HospitalUser):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    doctor_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    specialization_id = db.Column(db.Integer, db.ForeignKey("specializations.id"), nullable=False)
    department = db.Column(db.String(80))
    qualification = db.Column(db.String(120))
    experience_years = db.Column(db.Integer, default=0)
    bio = db.Column(db.String(500))
    fee_override = db.Column(Money)  # optional per-doctor fee; NULL = use specialization fee

    # Weekly schedule (hospital local time): comma-separated weekday numbers, Mon=0
    working_days = db.Column(db.String(20), nullable=False, default="0,1,2,3,4")
    start_time = db.Column(db.Time, nullable=False, default=time(9, 0))
    end_time = db.Column(db.Time, nullable=False, default=time(17, 0))
    slot_minutes = db.Column(db.Integer, nullable=False, default=30)
    accepting_appointments = db.Column(db.Boolean, nullable=False, default=True)

    user = db.relationship("User", backref=db.backref("doctor_profile", uselist=False))
    specialization = db.relationship("Specialization", backref="doctors")

    __table_args__ = (db.CheckConstraint("slot_minutes BETWEEN 10 AND 120", name="ck_doctor_slot"),)

    @property
    def working_day_numbers(self):
        return [int(d) for d in (self.working_days or "").split(",") if d.strip().isdigit()]

    @property
    def working_days_label(self):
        return ", ".join(WEEKDAYS[d] for d in self.working_day_numbers) or "-"

    @property
    def is_bookable(self) -> bool:
        """Doctor must be switched on by admin AND have an active login."""
        return bool(self.accepting_appointments and self.user and self.user.active)

    @property
    def base_fee(self) -> Decimal:
        return to_money(self.fee_override if self.fee_override is not None
                        else self.specialization.base_fee)

    def calculate_consultation_fee(self, follow_up: bool = False) -> Decimal:
        """POLYMORPHISM: delegates to the specialization's own override."""
        return get_policy(self.specialization.policy_key).calculate_consultation_fee(
            self.base_fee, follow_up)

    def display_details(self) -> dict:
        details = super().display_details()
        details.update({
            "Doctor ID": self.doctor_code,
            "Specialization": self.specialization.name,
            "Department": self.department or "-",
            "Consultation fee": f"₹{self.calculate_consultation_fee():,.2f}",
        })
        return details

    def __str__(self):
        return f"Dr. {self.full_name} ({self.specialization.name})"
