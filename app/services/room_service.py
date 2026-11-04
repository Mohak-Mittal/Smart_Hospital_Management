"""Room allocation and room charges."""
import math
from decimal import Decimal

from app.extensions import db
from app.models import RoomAssignment
from app.models.activity import log_activity
from app.models.types import to_money
from app.utils.timeutil import hospital_now


class RoomError(Exception):
    pass


def assign_room(room, patient, user=None) -> RoomAssignment:
    if not room.active:
        raise RoomError("This room is not in service.")
    if room.is_occupied:
        raise RoomError(f"Room {room.room_number} is already occupied.")
    existing = RoomAssignment.query.filter_by(patient_id=patient.id, released_at=None).first()
    if existing:
        raise RoomError(f"{patient.full_name} already occupies room {existing.room.room_number}.")
    assignment = RoomAssignment(room_id=room.id, patient_id=patient.id, assigned_at=hospital_now(),
                                assigned_by_user_id=getattr(user, "id", None))
    db.session.add(assignment)
    log_activity(f"Room {room.room_number} assigned to {patient.patient_code}", user)
    db.session.commit()
    return assignment


def release_assignment(assignment: RoomAssignment, user=None, commit=True):
    if assignment.released_at is not None:
        raise RoomError("This room has already been released.")
    assignment.released_at = hospital_now()
    log_activity(f"Room {assignment.room.room_number} released", user)
    if commit:
        db.session.commit()


def stay_days(assignment: RoomAssignment, until=None) -> int:
    """Each STARTED 24-hour period counts as one day; minimum 1 day."""
    end = until or assignment.released_at or hospital_now()
    seconds = max((end - assignment.assigned_at).total_seconds(), 0)
    return max(1, math.ceil(seconds / 86400))


def calculate_room_charge(assignment: RoomAssignment, until=None) -> Decimal:
    return to_money(assignment.room.room_type.daily_rate * stay_days(assignment, until))
