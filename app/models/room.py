from decimal import Decimal

from app.extensions import db
from app.models.types import Money
from app.utils.timeutil import hospital_now


class RoomType(db.Model):
    """Daily rate lives in the database so admins can change it."""
    __tablename__ = "room_types"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    daily_rate = db.Column(Money, nullable=False, default=Decimal("0.00"))

    def __str__(self):
        return self.name


class Room(db.Model):
    __tablename__ = "rooms"
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(20), unique=True, nullable=False)
    room_type_id = db.Column(db.Integer, db.ForeignKey("room_types.id"), nullable=False)
    floor = db.Column(db.String(20))
    active = db.Column(db.Boolean, nullable=False, default=True)

    room_type = db.relationship("RoomType", backref="rooms")

    @property
    def current_assignment(self):
        return RoomAssignment.query.filter_by(room_id=self.id, released_at=None).first()

    @property
    def is_occupied(self):
        return self.current_assignment is not None

    def __str__(self):
        return f"{self.room_type.name} {self.room_number}"


class RoomAssignment(db.Model):
    """A patient's stay in a room.  released_at NULL = still occupying it."""
    __tablename__ = "room_assignments"
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=hospital_now)
    released_at = db.Column(db.DateTime)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"))
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    room = db.relationship("Room", backref=db.backref("assignments", lazy="dynamic"))
    patient = db.relationship("Patient", backref=db.backref("room_assignments", lazy="dynamic"))

    __table_args__ = (
        # at most ONE active stay per room and per patient (enforced by the database too)
        db.Index("uq_room_active", "room_id", unique=True, sqlite_where=db.text("released_at IS NULL")),
        db.Index("uq_patient_room_active", "patient_id", unique=True, sqlite_where=db.text("released_at IS NULL")),
    )
