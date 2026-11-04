"""Emergency cases + Discharge record."""
from app.extensions import db
from app.utils.timeutil import hospital_now

PRIORITY_LABELS = {1: "Critical", 2: "Serious", 3: "Moderate", 4: "Minor"}
EMERGENCY_STATUSES = ("waiting", "in_treatment", "resolved")


class EmergencyCase(db.Model):
    __tablename__ = "emergency_cases"

    id = db.Column(db.Integer, primary_key=True)
    case_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"))      # NULL = walk-in, not registered
    patient_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer)
    complaint = db.Column(db.String(255), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=3, index=True)  # 1 = most urgent
    status = db.Column(db.String(20), nullable=False, default="waiting", index=True)
    arrived_at = db.Column(db.DateTime, nullable=False, default=hospital_now)
    assigned_doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    patient = db.relationship("Patient", backref=db.backref("emergency_cases", lazy="dynamic"))
    assigned_doctor = db.relationship("Doctor")

    __table_args__ = (
        db.CheckConstraint("priority BETWEEN 1 AND 4", name="ck_emergency_priority"),
        db.CheckConstraint("status IN ('waiting','in_treatment','resolved')", name="ck_emergency_status"),
    )

    @property
    def priority_label(self):
        return PRIORITY_LABELS.get(self.priority, "Unknown")

    def _sort_key(self):
        # Lower priority NUMBER = more urgent = comes first.  Ties: earlier arrival first.
        return (self.priority, self.arrived_at, self.id if self.id is not None else float("inf"))

    def __lt__(self, other):
        """MAGIC METHOD: a < b means 'a should be treated before b'."""
        if not isinstance(other, EmergencyCase):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def __str__(self):
        return f"[{self.priority_label}] {self.patient_name}: {self.complaint}"


class Discharge(db.Model):
    __tablename__ = "discharges"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    discharged_at = db.Column(db.DateTime, nullable=False, default=hospital_now)
    discharged_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    room_released = db.Column(db.String(60))
    notes = db.Column(db.String(255))

    patient = db.relationship("Patient", backref=db.backref("discharges", lazy="dynamic"))
    discharged_by = db.relationship("User")
