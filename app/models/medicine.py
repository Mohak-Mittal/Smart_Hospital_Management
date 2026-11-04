from decimal import Decimal

from app.extensions import db
from app.models.types import Money
from app.utils.timeutil import hospital_now


class Medicine(db.Model):
    __tablename__ = "medicines"

    id = db.Column(db.Integer, primary_key=True)
    medicine_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False)
    price = db.Column(Money, nullable=False, default=Decimal("0.00"))
    quantity = db.Column(db.Integer, nullable=False, default=0)       # available quantity
    reorder_level = db.Column(db.Integer, nullable=False, default=10)
    active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.CheckConstraint("quantity >= 0", name="ck_medicine_qty_nonneg"),  # DB-level safety net
        db.CheckConstraint("price >= 0", name="ck_medicine_price_nonneg"),
    )

    @property
    def is_low(self):
        return self.quantity <= self.reorder_level

    def __str__(self):
        return f"{self.name} ({self.quantity} in stock)"


class StockMovement(db.Model):
    """Audit trail: every add/remove of stock."""
    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"), nullable=False, index=True)
    change = db.Column(db.Integer, nullable=False)          # +added / -removed
    balance_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(120))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=hospital_now)

    medicine = db.relationship("Medicine", backref=db.backref("movements", lazy="dynamic"))
    user = db.relationship("User")
