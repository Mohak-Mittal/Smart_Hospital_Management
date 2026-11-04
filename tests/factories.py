"""Helpers that build test data quickly (used by every test file)."""
from datetime import timedelta
from decimal import Decimal
from itertools import count

from app.extensions import db
from app.models import Doctor, InsurancePolicy, Nurse, Patient, Room, RoomType, Specialization, User
from app.services import appointment_service, payment_service
from app.utils.id_generator import finalize_code, temp_code
from app.utils.timeutil import hospital_now

PASSWORD = "Demo@12345"
_n = count(1)


def ensure_reference_data():
    if Specialization.query.count():
        return
    for name, key, fee in [("General Physician", "general", 500), ("Cardiologist", "cardiologist", 1500),
                           ("Neurologist", "neurologist", 1800), ("Surgeon", "surgeon", 2500)]:
        db.session.add(Specialization(name=name, policy_key=key, base_fee=Decimal(fee)))
    for name, rate in [("General Ward", 1000), ("Private Room", 3000), ("ICU", 7000), ("Emergency Room", 5000)]:
        db.session.add(RoomType(name=name, daily_rate=Decimal(rate)))
    db.session.commit()


def make_user(role, name=None, email=None):
    i = next(_n)
    u = User(email=email or f"{role}{i}@test.demo", name=name or f"{role.title()} {i}", role=role)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.flush()
    return u


def make_admin():
    u = make_user("admin")
    db.session.commit()
    return u


def make_patient(name=None, email=None):
    ensure_reference_data()
    u = make_user("patient", name, email)
    p = Patient(patient_code=temp_code(), user=u, phone="9876543210")
    db.session.add(p)
    finalize_code(p, "PAT", "patient_code")
    db.session.commit()
    return p


def make_doctor(spec="general", name=None, email=None):
    ensure_reference_data()
    u = make_user("doctor", name, email)
    s = Specialization.query.filter_by(policy_key=spec).first()
    d = Doctor(doctor_code=temp_code(), user=u, specialization_id=s.id, working_days="0,1,2,3,4,5,6")
    db.session.add(d)
    finalize_code(d, "DOC", "doctor_code")
    db.session.commit()
    return d


def make_nurse():
    u = make_user("nurse")
    n = Nurse(nurse_code=temp_code(), user=u, ward="W1")
    db.session.add(n)
    finalize_code(n, "NUR", "nurse_code")
    db.session.commit()
    return n


def make_room(number="R-1", type_name="General Ward"):
    ensure_reference_data()
    t = RoomType.query.filter_by(name=type_name).first()
    r = Room(room_number=number, room_type_id=t.id)
    db.session.add(r)
    db.session.commit()
    return r


def make_policy(patient, pct="80", cap="30000", status="active"):
    p = InsurancePolicy(patient_id=patient.id, policy_number=f"POL-{next(_n):05d}-1234", company_name="TestCare",
                        coverage_percent=Decimal(pct), max_coverage=Decimal(cap), status=status,
                        valid_until=hospital_now().date() + timedelta(days=100))
    db.session.add(p)
    db.session.commit()
    return p


def free_slot(doctor, skip=0):
    """A real free slot in the future (searches the next 20 days)."""
    found = []
    for i in range(1, 21):
        found += appointment_service.available_slots(doctor, hospital_now().date() + timedelta(days=i))
        if len(found) > skip:
            return found[skip]
    raise AssertionError("no slot")


def paid_appointment(patient, doctor, skip=0):
    appt = appointment_service.book_appointment(patient, doctor, free_slot(doctor, skip), "test")
    payment_service.pay_appointment(appt, "upi", {"upi_id": "me@bank"}, patient.user)
    return appt


GOOD_CARD = {"card_name": "T Tester", "card_number": "4242 4242 4242 4242", "card_expiry": "12/40", "card_cvv": "123"}
