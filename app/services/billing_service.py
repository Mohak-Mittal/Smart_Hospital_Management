"""Creating bills, applying insurance and keeping the payment status correct."""
from decimal import Decimal

from app.extensions import db
from app.models import Appointment, Bill, BillItem, PaymentTransaction, RoomAssignment, TreatmentPlan
from app.models.activity import log_activity
from app.models.bill import ChargeSummary
from app.models.types import to_money
from app.services import inventory_service, room_service
from app.utils.id_generator import finalize_code, temp_code

ZERO = Decimal("0.00")


class BillingError(Exception):
    pass


def refresh_status(bill: Bill):
    """PAID when nothing is left to pay, PARTIALLY_PAID when some was paid, else PENDING."""
    if bill.balance_due <= 0:
        bill.status = "PAID"
    elif bill.amount_paid > 0:
        bill.status = "PARTIALLY_PAID"
    else:
        bill.status = "PENDING"


def calculate_insurance(policy, subtotal) -> Decimal:
    """Insurer share, capped by the bill amount and the policy maximum."""
    return policy.calculate_coverage(subtotal) if policy else ZERO


def _add_item(bill, category, description, qty, unit_price):
    amount = to_money(Decimal(unit_price) * qty)
    bill.items.append(BillItem(category=category, description=description[:255], quantity=qty,
                               unit_price=to_money(unit_price), amount=amount))
    return amount


def create_bill(patient, user, apply_insurance=True, dispense_items=(), notes="") -> Bill:
    """Collect everything not yet billed for this patient into ONE itemised bill.

    * consultation: paid, unbilled appointments (fee already collected at booking
      -> counted as already paid by the patient)
    * treatment / emergency: in-progress or completed treatment plans (cost from the
      polymorphic Treatment classes; 'emergency' type goes on the emergency line)
    * room: stays not yet billed (charged up to now; each started 24h = 1 day, min 1)
    * medicine: pharmacy items the admin dispenses now (stock is reduced)
    """
    appts = Appointment.query.filter(
        Appointment.patient_id == patient.id, Appointment.bill_id.is_(None),
        Appointment.payment_status == "paid", Appointment.status.in_(("scheduled", "completed"))).all()
    plans = TreatmentPlan.query.filter(
        TreatmentPlan.patient_id == patient.id, TreatmentPlan.bill_id.is_(None),
        TreatmentPlan.status.in_(("in_progress", "completed"))).all()
    stays = RoomAssignment.query.filter_by(patient_id=patient.id, bill_id=None).all()
    dispense_items = [(m, q) for m, q in dispense_items if m is not None and q]
    if not (appts or plans or stays or dispense_items):
        raise BillingError("There is nothing new to bill for this patient.")

    try:
        bill = Bill(invoice_number=temp_code(), patient_id=patient.id, notes=(notes or "")[:255] or None,
                    created_by_user_id=getattr(user, "id", None))
        db.session.add(bill)
        finalize_code(bill, "INV", "invoice_number")

        consult = ZERO
        for a in appts:
            consult += _add_item(bill, "consultation",
                                 f"Consultation - Dr. {a.doctor.full_name} ({a.start_time:%d %b %Y})", 1, a.fee)
            a.bill_id = bill.id
            for txn in a.payments.filter_by(status="success"):
                txn.bill_id = bill.id           # prepaid fee shows in this bill's payment history
        bill.consultation_fee = to_money(consult)
        prepaid = to_money(consult)

        treat = emerg = ZERO
        for p in plans:
            cost = p.cost
            label = f"{p.type_label} - {p.diagnosis or p.code}"
            _add_item(bill, "emergency" if p.treatment_type == "emergency" else "treatment", label, 1, cost)
            if p.treatment_type == "emergency":
                emerg += cost
            else:
                treat += cost
            p.bill_id = bill.id
        bill.treatment_charges, bill.emergency_charges = to_money(treat), to_money(emerg)

        room_total = ZERO
        for s in stays:
            days = room_service.stay_days(s)
            charge = room_service.calculate_room_charge(s)
            _add_item(bill, "room", f"{s.room.room_type.name} {s.room.room_number} - {days} day(s)",
                      days, s.room.room_type.daily_rate)
            room_total += charge
            s.bill_id = bill.id
        bill.room_charges = to_money(room_total)

        med_total = ZERO
        if dispense_items:
            inventory_service.dispense(dispense_items, f"Dispensed - {bill.invoice_number}", user)
            for med, qty in dispense_items:
                med_total += _add_item(bill, "medicine", med.name, int(qty), med.price)
        bill.medicine_charges = to_money(med_total)

        policy = patient.active_policy if apply_insurance else None
        if policy:
            bill.insurance_policy_id = policy.id
            bill.insurance_coverage = calculate_insurance(policy, bill.subtotal)
        bill.amount_paid = min(prepaid, bill.final_amount) if prepaid else ZERO
        refresh_status(bill)
        log_activity(f"Bill {bill.invoice_number} created for {patient.patient_code}", user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return bill


def summarize(bills) -> ChargeSummary:
    """Add several bills' charges together using ChargeSummary.__add__."""
    total = ChargeSummary()
    for b in bills:
        total = total + ChargeSummary(
            consultation_fee=b.consultation_fee, treatment_charges=b.treatment_charges,
            medicine_charges=b.medicine_charges, room_charges=b.room_charges,
            emergency_charges=b.emergency_charges)
    return total


def outstanding_for_patient(patient) -> Decimal:
    return to_money(sum((b.balance_due for b in patient.bills), ZERO))
