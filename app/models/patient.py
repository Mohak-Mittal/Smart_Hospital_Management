"""Patient profile - demonstrates ENCAPSULATION and the __eq__ magic method."""
from decimal import Decimal

from app.extensions import db
from app.models.types import Money, to_money
from app.models.user import HospitalUser
from app.utils.timeutil import hospital_now

BLOOD_GROUPS = ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
GENDERS = ["", "Female", "Male", "Other", "Prefer not to say"]


class Patient(HospitalUser):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    patient_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(20))
    blood_group = db.Column(db.String(5))
    address = db.Column(db.String(255))
    emergency_contact = db.Column(db.String(120))

    # ENCAPSULATION: a double underscore makes Python rename these attributes to
    # _Patient__medical_history / _Patient__wallet_balance ("name mangling").
    # This only DISCOURAGES accidental outside access - it is NOT security.
    # Real protection = login + role checks on every route (see utils/decorators
    # and routes/*).  Code should use the properties/methods below instead.
    __medical_history = db.Column("medical_history", db.Text, default="")
    __wallet_balance = db.Column("wallet_balance", Money, default=Decimal("0.00"), nullable=False)

    user = db.relationship("User", backref=db.backref("patient_profile", uselist=False))

    # ----- medical history (controlled access) -----
    @property
    def medical_history(self) -> str:
        return self.__medical_history or ""

    @medical_history.setter
    def medical_history(self, text: str):
        self.__medical_history = (text or "").strip()[:4000]

    @property
    def record_count(self) -> int:
        """Number of medical reports on file (instead of __len__, which would
        make an empty record 'falsy' and cause surprising `if patient:` bugs)."""
        return len(self.reports)

    # ----- wallet (controlled access: no negative balance) -----
    @property
    def wallet_balance(self) -> Decimal:
        return self.__wallet_balance or Decimal("0.00")

    def credit_wallet(self, amount) -> Decimal:
        amount = to_money(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        self.__wallet_balance = self.wallet_balance + amount
        return self.wallet_balance

    def debit_wallet(self, amount) -> Decimal:
        amount = to_money(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        if amount > self.wallet_balance:
            raise ValueError("Insufficient wallet balance.")
        self.__wallet_balance = self.wallet_balance - amount
        return self.wallet_balance

    # ----- insurance -----
    @property
    def active_policy(self):
        today = hospital_now().date()
        for policy in self.insurance_policies:
            if policy.is_valid_on(today):
                return policy
        return None

    @property
    def insurance_number(self) -> str:
        """Masked policy number, e.g. ****4821 (full number is admin-only)."""
        policy = self.active_policy
        return policy.masked_number if policy else ""

    # ----- polymorphism / magic methods -----
    def display_details(self) -> dict:
        details = super().display_details()
        details.update({
            "Patient ID": self.patient_code,
            "Blood group": self.blood_group or "-",
            "Date of birth": self.date_of_birth.strftime("%d %b %Y") if self.date_of_birth else "-",
            "Insurance": self.insurance_number or "None",
        })
        return details

    def __str__(self):
        return f"Patient {self.patient_code}: {self.full_name}"

    def __eq__(self, other):
        """Two patient objects are equal when they have the same patient ID."""
        if not isinstance(other, Patient):
            return NotImplemented
        return self.patient_code is not None and self.patient_code == other.patient_code

    def __hash__(self):
        return hash(("Patient", self.patient_code))
