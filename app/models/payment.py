"""Payments.

`Payment` (ABC) + UPI/Card/Cash/Insurance subclasses = behaviour
(ABSTRACTION + POLYMORPHISM: each overrides process_payment()).
`PaymentTransaction` (ORM) = the saved record.

ALL PAYMENTS ARE SIMULATED - NO REAL MONEY IS CHARGED and no network call is made.
Full card numbers and CVVs are validated in memory only and NEVER stored.
"""
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from app.extensions import db
from app.models.types import Money, to_money
from app.utils.timeutil import hospital_now
from app.utils.validators import card_brand, expiry_is_future, is_valid_upi, luhn_ok

DEMO_NOTICE = "DEMO PAYMENT — NO REAL MONEY IS CHARGED"
DECLINED_DEMO_CARD = "4000000000000002"   # always declined (like gateway test cards)
SUCCESS_DEMO_CARD = "4242424242424242"


@dataclass
class PaymentResult:
    success: bool
    reference: str = ""
    message: str = ""
    amount: Decimal = Decimal("0.00")
    detail: str = ""          # safe summary, e.g. "Visa ****4242"
    covered_amount: Decimal = Decimal("0.00")


def _ref(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(5).upper()}"


class Payment(ABC):
    method = ""
    label = ""

    def __init__(self, amount, **details):
        self.amount = to_money(amount)
        self.details = details

    @abstractmethod
    def process_payment(self) -> PaymentResult:
        """Validate + (pretend to) process.  Must never raise for bad input."""

    def display_details(self) -> str:
        return f"{self.label} payment of ₹{self.amount:,.2f}"

    def _fail(self, message) -> PaymentResult:
        return PaymentResult(False, "", message, self.amount)


class UPIPayment(Payment):
    method, label = "upi", "UPI"

    def process_payment(self):
        upi_id = (self.details.get("upi_id") or "").strip()
        if self.amount <= 0:
            return self._fail("Amount must be greater than zero.")
        if not is_valid_upi(upi_id):
            return self._fail("Enter a valid UPI ID such as name@bank.")
        if upi_id.lower().endswith("@fail"):                       # demo failure trigger
            return self._fail("UPI payment declined by the demo gateway.")
        return PaymentResult(True, _ref("UPI"), "UPI payment successful (demo).", self.amount,
                             detail=f"UPI {upi_id.split('@')[0][:2]}***@{upi_id.split('@')[1]}")


class CardPayment(Payment):
    method, label = "card", "Card"

    def process_payment(self):
        import re
        number = re.sub(r"[\s-]", "", self.details.get("card_number") or "")
        cvv = (self.details.get("card_cvv") or "").strip()
        expiry = self.details.get("card_expiry") or ""
        name = (self.details.get("card_name") or "").strip()
        if self.amount <= 0:
            return self._fail("Amount must be greater than zero.")
        if not name:
            return self._fail("Enter the name on the card.")
        if not number.isdigit() or not luhn_ok(number):
            return self._fail("The card number is not valid.")
        if not expiry_is_future(expiry, hospital_now().date()):
            return self._fail("The card has expired or the expiry date is invalid (use MM/YY).")
        if not (cvv.isdigit() and len(cvv) in (3, 4)):
            return self._fail("Enter a valid 3 or 4 digit CVV.")
        if number == DECLINED_DEMO_CARD:
            return self._fail("Card declined by the demo gateway.")
        # Only the brand + last 4 digits are kept.  number/cvv go out of scope here.
        return PaymentResult(True, _ref("CARD"), "Card payment successful (demo).", self.amount,
                             detail=f"{card_brand(number)} ****{number[-4:]}")


class CashPayment(Payment):
    method, label = "cash", "Cash"

    def process_payment(self):
        if self.amount <= 0:
            return self._fail("Amount must be greater than zero.")
        return PaymentResult(True, _ref("RCPT"), "Cash received - receipt issued (demo).",
                             self.amount, detail="Cash receipt")


class InsurancePayment(Payment):
    """Insurer settlement: verifies the policy and works out the covered amount."""
    method, label = "insurance", "Insurance"

    def process_payment(self):
        policy = self.details.get("policy")
        if policy is None:
            return self._fail("No insurance policy is linked.")
        if not policy.is_valid_on(hospital_now().date()):
            return self._fail("The insurance policy is not active or has expired.")
        covered = policy.calculate_coverage(self.amount)
        if covered <= 0:
            return self._fail("The policy does not cover this amount.")
        return PaymentResult(True, _ref("INS"), "Insurance claim accepted (demo).", covered,
                             detail=f"{policy.company_name} {policy.masked_number}",
                             covered_amount=covered)


PAYMENT_REGISTRY = {c.method: c for c in (UPIPayment, CardPayment, CashPayment, InsurancePayment)}


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    txn_ref = db.Column(db.String(30), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), index=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), index=True)
    kind = db.Column(db.String(20), nullable=False, default="consultation")  # consultation|bill|insurer
    method = db.Column(db.String(20), nullable=False)
    amount = db.Column(Money, nullable=False, default=Decimal("0.00"))
    status = db.Column(db.String(20), nullable=False, default="success")    # success|failed
    detail = db.Column(db.String(120))      # safe summary only (never full card data)
    message = db.Column(db.String(255))
    counts_toward_balance = db.Column(db.Boolean, nullable=False, default=True)
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=hospital_now)

    patient = db.relationship("Patient", backref=db.backref("payments", lazy="dynamic"))
    appointment = db.relationship("Appointment", backref=db.backref("payments", lazy="dynamic"))
    bill = db.relationship("Bill", backref=db.backref("payments", lazy="dynamic"))

    __table_args__ = (
        db.CheckConstraint("method IN ('upi','card','cash','insurance')", name="ck_txn_method"),
        db.CheckConstraint("status IN ('success','failed')", name="ck_txn_status"),
    )
