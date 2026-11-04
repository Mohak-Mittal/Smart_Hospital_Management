from app.extensions import db
from app.models.user import HospitalUser

# which patients a nurse looks after (many-to-many)
nurse_patients = db.Table(
    "nurse_patients",
    db.Column("nurse_id", db.Integer, db.ForeignKey("nurses.id"), primary_key=True),
    db.Column("patient_id", db.Integer, db.ForeignKey("patients.id"), primary_key=True),
)


class Nurse(HospitalUser):
    __tablename__ = "nurses"

    id = db.Column(db.Integer, primary_key=True)
    nurse_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    ward = db.Column(db.String(80))
    shift = db.Column(db.String(30), default="Day")

    user = db.relationship("User", backref=db.backref("nurse_profile", uselist=False))
    assigned_patients = db.relationship("Patient", secondary=nurse_patients,
                                        backref=db.backref("nurses", lazy="select"))

    def display_details(self) -> dict:
        details = super().display_details()
        details.update({"Nurse ID": self.nurse_code, "Ward": self.ward or "-", "Shift": self.shift or "-"})
        return details
