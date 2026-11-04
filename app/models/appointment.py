from decimal import Decimal

from app.extensions import db
from app.models.types import Money
from app.utils.timeutil import hospital_now

APPOINTMENT_STATUSES = ("pending", "scheduled", "completed", "cancelled", "emergency")
PAYMENT_STATUSES = ("pending", "paid", "refunded", "partially_refunded")
# statuses that occupy a doctor's time slot
SLOT_BLOCKING = ("pending", "scheduled", "completed")


class Appointment(db.Model):
    """One booking.  `pending` = slot held, waiting for the (simulated) payment."""
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    payment_status = db.Column(db.String(20), nullable=False, default="pending")
    fee = db.Column(Money, nullable=False, default=Decimal("0.00"))
    refund_amount = db.Column(Money, nullable=False, default=Decimal("0.00"))
    reason = db.Column(db.String(255))
    diagnosis = db.Column(db.Text)
    consultation_notes = db.Column(db.Text)
    consultation_recorded_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=hospital_now)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"))

    patient = db.relationship("Patient", backref=db.backref("appointments", lazy="dynamic"))
    doctor = db.relationship("Doctor", backref=db.backref("appointments", lazy="dynamic"))

    __table_args__ = (
        # DB-level guard against double booking: one active booking per doctor+start time.
        db.Index("uq_doctor_active_slot", "doctor_id", "start_time", unique=True,
                 sqlite_where=db.text("status IN ('pending','scheduled','completed')")),
        db.CheckConstraint("status IN ('pending','scheduled','completed','cancelled','emergency')",
                           name="ck_appt_status"),
        db.CheckConstraint("payment_status IN ('pending','paid','refunded','partially_refunded')",
                           name="ck_appt_paystatus"),
    )

    @property
    def is_paid(self):
        return self.payment_status == "paid"

    def __str__(self):
        return f"Appointment {self.code} on {self.start_time:%d %b %Y %H:%M} ({self.status})"
