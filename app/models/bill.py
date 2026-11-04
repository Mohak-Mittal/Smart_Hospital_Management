from decimal import Decimal

from app.extensions import db
from app.models.types import Money, to_money
from app.utils.timeutil import hospital_now

ZERO = Decimal("0.00")
BILL_STATUSES = ("PENDING", "PARTIALLY_PAID", "PAID")


class Bill(db.Model):
    """An invoice.

    Money model (avoids double counting insurance):
      subtotal          = all charges
      insurance_coverage= what the INSURER owes (a share of the subtotal, not a payment)
      final_amount      = subtotal - insurance_coverage   <- the PATIENT's share
      amount_paid       = payments made by the patient toward final_amount
      balance_due       = final_amount - amount_paid
    The insurer settling its share is tracked separately by `insurer_settled`.
    """
    __tablename__ = "bills"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    insurance_policy_id = db.Column(db.Integer, db.ForeignKey("insurance_policies.id"))
    consultation_fee = db.Column(Money, nullable=False, default=ZERO)
    treatment_charges = db.Column(Money, nullable=False, default=ZERO)
    medicine_charges = db.Column(Money, nullable=False, default=ZERO)
    room_charges = db.Column(Money, nullable=False, default=ZERO)
    emergency_charges = db.Column(Money, nullable=False, default=ZERO)
    insurance_coverage = db.Column(Money, nullable=False, default=ZERO)
    amount_paid = db.Column(Money, nullable=False, default=ZERO)
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    insurer_settled = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.String(255))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=hospital_now)

    patient = db.relationship("Patient", backref=db.backref("bills", lazy="dynamic"))
    policy = db.relationship("InsurancePolicy")
    items = db.relationship("BillItem", backref="bill", cascade="all, delete-orphan",
                            order_by="BillItem.id")

    __table_args__ = (
        db.CheckConstraint("status IN ('PENDING','PARTIALLY_PAID','PAID')", name="ck_bill_status"),
    )

    @property
    def subtotal(self) -> Decimal:
        return to_money(self.consultation_fee + self.treatment_charges + self.medicine_charges
                        + self.room_charges + self.emergency_charges)

    @property
    def final_amount(self) -> Decimal:
        return to_money(self.subtotal - self.insurance_coverage)

    @property
    def balance_due(self) -> Decimal:
        return max(to_money(self.final_amount - self.amount_paid), ZERO)

    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.status})"


class BillItem(db.Model):
    __tablename__ = "bill_items"
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(Money, nullable=False, default=ZERO)
    amount = db.Column(Money, nullable=False, default=ZERO)


class ChargeSummary:
    """Small value object showing the __add__ magic method: summaries can be added."""

    def __init__(self, **amounts):
        keys = ("consultation_fee", "treatment_charges", "medicine_charges",
                "room_charges", "emergency_charges")
        self.amounts = {k: to_money(amounts.get(k, 0)) for k in keys}

    @property
    def total(self) -> Decimal:
        return to_money(sum(self.amounts.values(), ZERO))

    def __add__(self, other):
        if not isinstance(other, ChargeSummary):
            return NotImplemented
        return ChargeSummary(**{k: self.amounts[k] + other.amounts[k] for k in self.amounts})

    def __str__(self):
        return f"ChargeSummary(total=₹{self.total:,.2f})"
