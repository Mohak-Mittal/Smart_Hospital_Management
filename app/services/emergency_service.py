"""Emergency queue (priority queue built on heapq)."""
import heapq
import itertools
from datetime import timedelta

from app.extensions import db
from app.models import Appointment, EmergencyCase
from app.models.activity import log_activity
from app.models.emergency import PRIORITY_LABELS
from app.utils.id_generator import finalize_code, temp_code
from app.utils.timeutil import hospital_now


class EmergencyError(Exception):
    pass


class EmergencyQueue:
    """Min-heap of cases: Level 1 comes out first; equal levels leave in arrival order.

    heapq compares items with `<`, which for EmergencyCase is its __lt__.
    The extra sequence number makes ties fully deterministic (first in, first out).
    """

    class _Entry:
        __slots__ = ("case", "seq")

        def __init__(self, case, seq):
            self.case, self.seq = case, seq

        def __lt__(self, other):
            if self.case < other.case:
                return True
            if other.case < self.case:
                return False
            return self.seq < other.seq

    def __init__(self, cases=()):
        self._heap, self._seq = [], itertools.count()
        for case in cases:
            self.push(case)

    def push(self, case):
        heapq.heappush(self._heap, self._Entry(case, next(self._seq)))

    def pop(self):
        return heapq.heappop(self._heap).case

    def __len__(self):
        return len(self._heap)

    def ordered(self):
        """Non-destructive sorted list (pops from a copy)."""
        clone = EmergencyQueue()
        clone._heap, clone._seq = list(self._heap), self._seq
        out = []
        while len(clone):
            out.append(clone.pop())
        return out


def waiting_queue():
    cases = EmergencyCase.query.filter_by(status="waiting").all()
    return EmergencyQueue(cases).ordered()


def add_case(patient_name, complaint, priority, patient=None, age=None, user=None) -> EmergencyCase:
    priority = int(priority)
    if priority not in PRIORITY_LABELS:
        raise EmergencyError("Priority must be 1 (Critical) to 4 (Minor).")
    name = (patient.full_name if patient else (patient_name or "")).strip()
    if not name or not (complaint or "").strip():
        raise EmergencyError("Patient name and complaint are required.")
    case = EmergencyCase(case_code=temp_code(), patient_id=patient.id if patient else None,
                         patient_name=name, age=age, complaint=complaint.strip()[:255],
                         priority=priority, arrived_at=hospital_now(),
                         created_by_user_id=getattr(user, "id", None))
    db.session.add(case)
    finalize_code(case, "EMG", "case_code")
    log_activity(f"Emergency case {case.case_code} added ({PRIORITY_LABELS[priority]})", user)
    db.session.commit()
    return case


def set_priority(case, priority, user=None):
    priority = int(priority)
    if priority not in PRIORITY_LABELS:
        raise EmergencyError("Priority must be 1 (Critical) to 4 (Minor).")
    case.priority = priority
    log_activity(f"Emergency case {case.case_code} priority set to {PRIORITY_LABELS[priority]}", user)
    db.session.commit()


def set_status(case, status, user=None):
    if status not in ("waiting", "in_treatment", "resolved"):
        raise EmergencyError("Unknown status.")
    case.status = status
    log_activity(f"Emergency case {case.case_code} marked {status.replace('_', ' ')}", user)
    db.session.commit()


def assign_doctor(case, doctor, user=None):
    """Send the case to a doctor.  A registered patient also gets an 'emergency'
    appointment so the doctor is allowed to open the patient's record."""
    if not doctor.user.active:
        raise EmergencyError("That doctor's account is inactive.")
    case.assigned_doctor_id = doctor.id
    case.status = "in_treatment"
    if case.patient_id:
        now = hospital_now()
        appt = Appointment(code=temp_code(), patient_id=case.patient_id, doctor_id=doctor.id,
                           start_time=now, end_time=now + timedelta(minutes=30), status="emergency",
                           payment_status="pending", fee=0, reason=f"Emergency: {case.complaint}"[:255])
        db.session.add(appt)
        finalize_code(appt, "APT")
    log_activity(f"Emergency case {case.case_code} assigned to Dr. {doctor.full_name}", user)
    db.session.commit()
