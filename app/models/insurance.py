from decimal import Decimal

from app.extensions import db
from app.models.types import Money, to_money
from app.utils.timeutil import hospital_now


class InsurancePolicy(db.Model):
    __tablename__ = "insurance_policies"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    policy_number = db.Column(db.String(40), unique=True, nullable=False)
    company_name = db.Column(db.String(120), nullable=False)
    coverage_percent = db.Column(Money, nullable=False, default=Decimal("0.00"))  # e.g. 80.00
    max_coverage = db.Column(Money, nullable=False, default=Decimal("0.00"))      # rupee cap
    status = db.Column(db.String(20), nullable=False, default="active")           # active|expired|suspended
    valid_until = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=hospital_now)

    patient = db.relationship("Patient", backref=db.backref("insurance_policies", lazy="select"))

    __table_args__ = (
        db.CheckConstraint("coverage_percent >= 0 AND coverage_percent <= 10000", name="ck_policy_pct"),
        db.CheckConstraint("status IN ('active','expired','suspended')", name="ck_policy_status"),
    )

    @property
    def masked_number(self):
        return "****" + (self.policy_number or "")[-4:]

    def is_valid_on(self, day) -> bool:
        if self.status != "active":
            return False
        return self.valid_until is None or self.valid_until >= day

    def calculate_coverage(self, eligible_amount, on=None) -> Decimal:
        """Insurer share = min( amount x percent, policy maximum, amount ).

        Example: Rs 50,000 bill, 80%, max Rs 30,000 -> 40,000 capped to 30,000.
        Invalid / expired policies cover nothing.
        """
        day = on or hospital_now().date()
        amount = to_money(eligible_amount)
        if amount <= 0 or not self.is_valid_on(day):
            return Decimal("0.00")
        by_percent = to_money(amount * self.coverage_percent / Decimal("100"))
        return min(by_percent, to_money(self.max_coverage), amount)

    def __str__(self):
        return f"{self.company_name} {self.masked_number}"
