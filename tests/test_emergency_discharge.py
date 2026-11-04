from datetime import timedelta

import pytest

from app.extensions import db
from app.models import EmergencyCase, RoomAssignment, TreatmentPlan
from app.services import (billing_service, discharge_service, emergency_service, payment_service,
                          room_service, treatment_service)
from app.services.discharge_service import DischargeError
from app.services.emergency_service import EmergencyQueue
from app.utils.timeutil import hospital_now
from tests.factories import make_admin, make_doctor, make_patient, make_room


def _case(name, priority, minutes_ago=0):
    c = emergency_service.add_case(name, "complaint", priority)
    c.arrived_at = hospital_now() - timedelta(minutes=minutes_ago)
    db.session.commit()
    return c


def test_level_1_is_served_before_2_3_4(app):
    _case("minor", 4, 50); _case("moderate", 3, 40); _case("serious", 2, 30); _case("critical", 1, 1)
    assert [c.patient_name for c in emergency_service.waiting_queue()] == ["critical", "serious", "moderate", "minor"]


def test_equal_priority_keeps_arrival_order(app):
    _case("third", 2, 5); _case("first", 2, 30); _case("second", 2, 10)
    assert [c.patient_name for c in emergency_service.waiting_queue()] == ["first", "second", "third"]


def test_equal_priority_and_time_falls_back_to_insertion_order(app):
    now = hospital_now()
    cases = [EmergencyCase(patient_name=n, priority=2, arrived_at=now) for n in ("a", "b", "c")]
    assert [c.patient_name for c in EmergencyQueue(cases).ordered()] == ["a", "b", "c"]


def test_lt_direction_is_correct(app):
    now = hospital_now()
    critical, minor = EmergencyCase(priority=1, arrived_at=now), EmergencyCase(priority=4, arrived_at=now)
    assert critical < minor and not (minor < critical)          # smaller number = more urgent = "less than"
    earlier = EmergencyCase(priority=3, arrived_at=now - timedelta(minutes=5))
    assert earlier < EmergencyCase(priority=3, arrived_at=now)


def test_heap_pop_order_and_len(app):
    now = hospital_now()
    q = EmergencyQueue([EmergencyCase(patient_name="p3", priority=3, arrived_at=now),
                        EmergencyCase(patient_name="p1", priority=1, arrived_at=now)])
    assert len(q) == 2 and q.pop().patient_name == "p1" and len(q) == 1


def test_invalid_priority_rejected(app):
    with pytest.raises(emergency_service.EmergencyError):
        emergency_service.add_case("x", "y", 5)


def test_priority_change_reorders_queue(app):
    a, b = _case("a", 3, 20), _case("b", 3, 10)
    emergency_service.set_priority(b, 1)
    assert [c.patient_name for c in emergency_service.waiting_queue()] == ["b", "a"]


def test_assigning_registered_patient_gives_doctor_access(app):
    from app.services.access import doctor_can_access_patient
    p, d = make_patient(), make_doctor()
    case = emergency_service.add_case(None, "chest pain", 1, patient=p)
    assert not doctor_can_access_patient(d, p)
    emergency_service.assign_doctor(case, d)
    assert case.status == "in_treatment" and doctor_can_access_patient(d, p)


# ---------------------------------------------------------------- discharge
def _episode(complete=True, approve=True, bill=True, pay=True, room=True):
    p, d, admin = make_patient(), make_doctor(), make_admin()
    plan = treatment_service.create_plan(d, p, "medicine", "Dx", "", {"medicine_charges": "1000"})
    treatment_service.set_status(plan, "in_progress", d.user)
    if complete:
        treatment_service.set_status(plan, "completed", d.user)
    if approve and complete:
        treatment_service.approve_discharge(plan, d.user)
    r = make_room()
    if room:
        room_service.assign_room(r, p, admin)
    b = None
    if bill:
        b = billing_service.create_bill(p, admin, False, [])
        if pay:
            payment_service.pay_bill(b, "cash", b.balance_due, {}, admin)
    return p, plan, r, b, admin


def test_discharge_blocked_when_treatment_not_completed(app):
    p, plan, r, b, admin = _episode(complete=False, approve=False)
    check = discharge_service.evaluate(p)
    assert not check.eligible and "Treatment completed" in " ".join(check.unmet)
    with pytest.raises(DischargeError) as e:
        discharge_service.discharge_patient(p, admin)
    assert any("Treatment completed" in u for u in e.value.unmet) and r.is_occupied


def test_discharge_blocked_without_doctor_approval(app):
    p, plan, r, b, admin = _episode(approve=False)
    assert [c.key for c in discharge_service.evaluate(p).conditions if not c.met] == ["approval"]


def test_discharge_blocked_without_bill(app):
    p, plan, r, b, admin = _episode(bill=False, pay=False)
    unmet = [c.key for c in discharge_service.evaluate(p).conditions if not c.met]
    assert "bill" in unmet and "payment" in unmet


def test_discharge_blocked_with_outstanding_balance(app):
    p, plan, r, b, admin = _episode(pay=False)
    check = discharge_service.evaluate(p)
    assert [c.key for c in check.conditions if not c.met] == ["payment"]
    assert "balance due" in check.unmet[0]


def test_discharge_blocked_until_insurer_settles(app):
    from tests.factories import make_policy
    p, d, admin = make_patient(), make_doctor(), make_admin()
    make_policy(p, "50", "100000")
    plan = treatment_service.create_plan(d, p, "medicine", "Dx", "", {"medicine_charges": "1000"})
    treatment_service.set_status(plan, "in_progress", d.user); treatment_service.set_status(plan, "completed", d.user)
    treatment_service.approve_discharge(plan, d.user)
    b = billing_service.create_bill(p, admin, True, [])
    payment_service.pay_bill(b, "cash", b.balance_due, {}, admin)
    assert "insurer share not settled" in " ".join(discharge_service.evaluate(p).unmet)
    payment_service.settle_insurer(b, admin)
    assert discharge_service.evaluate(p).eligible


def test_successful_discharge_releases_room(app):
    p, plan, r, b, admin = _episode()
    assert r.is_occupied and discharge_service.evaluate(p).eligible
    rec = discharge_service.discharge_patient(p, admin)
    assert not r.is_occupied and rec.room_released and "General Ward" in rec.room_released
    assert db.session.get(TreatmentPlan, plan.id).discharged_at is not None
    with pytest.raises(DischargeError):                      # nothing left to discharge
        discharge_service.discharge_patient(p, admin)


def test_discharge_routes(app, login_as):
    p, plan, r, b, admin = _episode(pay=False)
    c = login_as(admin)
    resp = c.post(f"/admin/discharges/{p.id}", follow_redirects=True)
    assert b"Discharge denied" in resp.data and b"balance due" in resp.data
    payment_service.pay_bill(b, "cash", b.balance_due, {}, admin)
    resp = c.post(f"/admin/discharges/{p.id}", follow_redirects=True)
    assert b"has been discharged" in resp.data and not r.is_occupied
