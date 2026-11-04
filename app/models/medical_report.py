from app.extensions import db
from app.utils.timeutil import hospital_now


class MedicalReport(db.Model):
    """Doctor-authored report.  Patients only ever see `published` ones."""
    __tablename__ = "medical_reports"

    id = db.Column(db.Integer, primary_key=True)
    report_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"))
    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")  # draft|published
    created_at = db.Column(db.DateTime, default=hospital_now)
    published_at = db.Column(db.DateTime)

    patient = db.relationship("Patient", backref=db.backref("reports", lazy="select",
                                                            order_by="MedicalReport.created_at.desc()"))
    doctor = db.relationship("Doctor", backref=db.backref("reports", lazy="dynamic"))

    __table_args__ = (db.CheckConstraint("status IN ('draft','published')", name="ck_report_status"),)

    @property
    def is_published(self):
        return self.status == "published"
