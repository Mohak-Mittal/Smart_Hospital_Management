from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Medicine
from app.services import inventory_service, room_service
from app.services.inventory_service import InventoryError
from app.services.room_service import RoomError
from app.utils.timeutil import hospital_now
from tests.factories import make_admin, make_patient, make_room


def _med(qty=10):
    m = Medicine(medicine_code=f"M{Medicine.query.count()}", name="TestMed", category="Test", price=Decimal("5.50"), quantity=qty)
    db.session.add(m)
    db.session.commit()
    return m


def test_stock_cannot_go_negative(app):
    m = _med(5)
    with pytest.raises(InventoryError, match="Only 5"):
        inventory_service.remove_stock(m, 6)
    assert m.quantity == 5
    assert inventory_service.remove_stock(m, 5) == 0
    with pytest.raises(InventoryError):
        inventory_service.remove_stock(m, 1)


def test_database_constraint_is_a_second_safety_net(app):
    m = _med(1)
    m.quantity = -1
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_invalid_quantities_rejected(app):
    m = _med()
    for bad in (0, -3, "x", None):
        with pytest.raises(InventoryError):
            inventory_service.add_stock(m, bad)


def test_add_stock_cost_and_movement_history(app):
    m = _med(10)
    inventory_service.add_stock(m, 5, "delivery", make_admin())
    assert inventory_service.check_stock(m) == 15
    assert inventory_service.calculate_medicine_cost([(m, 4)]) == Decimal("22.00")
    assert [mv.change for mv in m.movements] == [5]


def test_dispense_is_all_or_nothing(app):
    a, b = _med(10), _med(1)
    with pytest.raises(InventoryError):
        inventory_service.dispense([(a, 3), (b, 2)], "test")
    assert a.quantity == 10 and b.quantity == 1


def test_occupied_room_cannot_be_assigned_again(app):
    room, p1, p2, admin = make_room(), make_patient(), make_patient(), make_admin()
    room_service.assign_room(room, p1, admin)
    assert room.is_occupied
    with pytest.raises(RoomError, match="already occupied"):
        room_service.assign_room(room, p2, admin)


def test_patient_cannot_occupy_two_rooms(app):
    r1, r2, p = make_room("A"), make_room("B"), make_patient()
    room_service.assign_room(r1, p)
    with pytest.raises(RoomError, match="already occupies"):
        room_service.assign_room(r2, p)


def test_release_makes_room_available_again(app):
    room, p1, p2 = make_room(), make_patient(), make_patient()
    a = room_service.assign_room(room, p1)
    room_service.release_assignment(a)
    assert not room.is_occupied
    room_service.assign_room(room, p2)
    assert room.is_occupied


def test_room_charge_rounding_and_minimum_day(app):
    room, p = make_room(type_name="ICU"), make_patient()
    a = room_service.assign_room(room, p)
    start = a.assigned_at
    assert room_service.calculate_room_charge(a, start + timedelta(minutes=5)) == Decimal("7000.00")      # minimum 1 day
    assert room_service.calculate_room_charge(a, start + timedelta(hours=24)) == Decimal("7000.00")
    assert room_service.calculate_room_charge(a, start + timedelta(hours=24, minutes=1)) == Decimal("14000.00")  # started 2nd day
    assert room_service.stay_days(a, start + timedelta(days=3)) == 3


def test_room_demo_rates(app):
    for name, rate in [("General Ward", 1000), ("Private Room", 3000), ("ICU", 7000), ("Emergency Room", 5000)]:
        assert make_room(f"R-{name}", name).room_type.daily_rate == Decimal(rate)


def test_inactive_room_cannot_be_assigned(app):
    room = make_room()
    room.active = False
    db.session.commit()
    with pytest.raises(RoomError, match="not in service"):
        room_service.assign_room(room, make_patient())
