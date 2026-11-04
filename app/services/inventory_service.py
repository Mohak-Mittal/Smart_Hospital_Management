"""Medicine stock rules: stock can never go below zero."""
from decimal import Decimal

from app.extensions import db
from app.models import Medicine, StockMovement
from app.models.types import to_money


class InventoryError(Exception):
    pass


def _positive_int(qty) -> int:
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise InventoryError("Quantity must be a whole number.")
    if qty <= 0:
        raise InventoryError("Quantity must be greater than zero.")
    return qty


def check_stock(medicine: Medicine) -> int:
    return medicine.quantity


def _move(medicine, change, reason, user):
    medicine.quantity += change
    db.session.add(StockMovement(medicine_id=medicine.id, change=change,
                                 balance_after=medicine.quantity, reason=(reason or "")[:120],
                                 user_id=getattr(user, "id", None)))


def add_stock(medicine: Medicine, qty, reason="Stock received", user=None, commit=True) -> int:
    qty = _positive_int(qty)
    _move(medicine, qty, reason, user)
    if commit:
        db.session.commit()
    return medicine.quantity


def remove_stock(medicine: Medicine, qty, reason="Stock removed", user=None, commit=True) -> int:
    qty = _positive_int(qty)
    if qty > medicine.quantity:
        raise InventoryError(f"Only {medicine.quantity} unit(s) of {medicine.name} available.")
    _move(medicine, -qty, reason, user)
    if commit:
        db.session.commit()
    return medicine.quantity


def calculate_medicine_cost(items) -> Decimal:
    """items = [(Medicine, quantity), ...] -> total price (no stock change)."""
    total = Decimal("0.00")
    for medicine, qty in items:
        total += medicine.price * _positive_int(qty)
    return to_money(total)


def dispense(items, reason, user=None):
    """Remove stock for several medicines all-or-nothing and return the total cost."""
    for medicine, qty in items:                          # check everything first
        if _positive_int(qty) > medicine.quantity:
            raise InventoryError(f"Only {medicine.quantity} unit(s) of {medicine.name} available.")
    total = calculate_medicine_cost(items)
    for medicine, qty in items:
        remove_stock(medicine, qty, reason, user, commit=False)
    return total
