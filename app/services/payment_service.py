"""Simulated payments for consultation fees and bills."""
from decimal import Decimal

from app.extensions import db
from app.models import PaymentTransaction
from app.models.activity import log_activity
from app.models.payment import PAYMENT_REGISTRY, Payment
from app.models.types import to_money
from app.services import billing_service
from app.utils.id_generator import finalize_code, temp_code

PATIENT_METHODS = ("upi", "card", "cash")      # methods a patient/receptionist can choose


class PaymentError(Exception):
    pass


def build_payment(method: str, amount, **details) -> Payment:
    """Factory: pick the right Payment subclass from the registry."""
    cls = PAYMENT_REGISTRY.get((method or "").strip().lower())
    if cls is None:
        raise PaymentError("Unsupported payment method.")
    return cls(amount, **details)


def _record(patient_id, method, result, amount, kind, user, appointment_id=None, bill_id=None,
            counts=True):
    txn = PaymentTransaction(
        txn_ref=temp_code(), patient_id=patient_id, appointment_id=appointment_id, bill_id=bill_id,
        kind=kind, method=method, amount=amount if result.success else to_money(amount),
        status="success" if result.success else "failed", detail=result.detail,
        message=result.message, counts_toward_balance=counts,
        recorded_by_user_id=getattr(user, "id", None))
    db.session.add(txn)
    finalize_code(txn, "TXN", "txn_ref", width=6)
    return txn


def pay_appointment(appointment, method: str, details: dict, user):
    """Pay the consultation fee.  Booking is confirmed ONLY if the payment succeeds."""
    if method not in PATIENT_METHODS:
        raise PaymentError("Unsupported payment method.")
    if appointment.status != "pending" or appointment.payment_status != "pending":
        raise PaymentError("This appointment is not waiting for payment (it may have expired).")
    payment = build_payment(method, appointment.fee, **details)
    result = payment.process_payment()          # NEVER trust client claims - we compute the outcome
    try:
        txn = _record(appointment.patient_id, method, result, appointment.fee, "consultation",
                      user, appointment_id=appointment.id)
        if result.success:
            appointment.payment_status = "paid"
            appointment.status = "scheduled"
            log_activity(f"Consultation payment received for {appointment.code}", user)
        db.session.commit()
    except Exception:
        db.session.rollback()   # all-or-nothing: no half-booked / half-paid states
        raise
    return txn


def pay_bill(bill, method: str, amount, details: dict, user):
    """Pay (part of) the patient's share of a bill."""
    if method not in PATIENT_METHODS:
        raise PaymentError("Unsupported payment method.")
    amount = to_money(amount)
    if amount <= 0:
        raise PaymentError("Enter an amount greater than zero.")
    if amount > bill.balance_due:
        raise PaymentError(f"Amount cannot exceed the balance due (₹{bill.balance_due:,.2f}).")
    result = build_payment(method, amount, **details).process_payment()
    try:
        txn = _record(bill.patient_id, method, result, amount, "bill", user, bill_id=bill.id)
        if result.success:
            bill.amount_paid = to_money(bill.amount_paid + amount)
            billing_service.refresh_status(bill)
            log_activity(f"Payment of ₹{amount:,.2f} recorded on {bill.invoice_number}", user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return txn


def settle_insurer(bill, user):
    """Record the insurer paying its share (kept apart from the patient's payments)."""
    if bill.insurance_coverage <= 0 or bill.policy is None:
        raise PaymentError("This bill has no insurance contribution to settle.")
    if bill.insurer_settled:
        raise PaymentError("The insurer share has already been settled.")
    payment = build_payment("insurance", bill.subtotal, policy=bill.policy)
    result = payment.process_payment()
    try:
        txn = _record(bill.patient_id, "insurance", result, bill.insurance_coverage, "insurer",
                      user, bill_id=bill.id, counts=False)
        if result.success:
            bill.insurer_settled = True
            log_activity(f"Insurer share settled on {bill.invoice_number}", user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return txn
