from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Bill
from app.models.bill import ChargeSummary
from app.services import billing_service, payment_service, treatment_service
from app.services.payment_service import PaymentError
from tests.factories import make_admin, make_doctor, make_patient, make_policy, make_room, paid_appointment


def test_insurance_capped_by_policy_maximum(app):
    pol = make_policy(make_patient(), pct="80", cap="30000")
    covered = pol.calculate_coverage(Decimal("50000"))
    assert covered == Decimal("30000.00")                      # the PDF example
    assert Decimal("50000") - covered == Decimal("20000")      # patient share


def test_insurance_percentage_when_below_cap_and_never_above_bill(app):
    pol = make_policy(make_patient(), pct="80", cap="30000")
    assert pol.calculate_coverage(Decimal("10000")) == Decimal("8000.00")
    full = make_policy(make_patient(), pct="100", cap="1000000")
    assert full.calculate_coverage(Decimal("999.99")) == Decimal("999.99")


def test_inactive_policy_covers_nothing(app):
    assert make_policy(make_patient(), status="suspended").calculate_coverage(Decimal("5000")) == 0


def _bill_with_treatment(patient, doctor, admin, cost="50000", insured=True):
    plan = treatment_service.create_plan(doctor, patient, "surgery", "Dx", "", {"operation_charges": cost, "surgeon_charges": "0.01"})
    treatment_service.set_status(plan, "in_progress", doctor.user)
    return billing_service.create_bill(patient, admin, insured, [])


def test_bill_applies_insurance_without_double_counting(app):
    p, d, admin = make_patient(), make_doctor("surgeon"), make_admin()
    make_policy(p, "80", "30000")
    bill = _bill_with_treatment(p, d, admin, "49999.99")
    assert bill.subtotal == Decimal("50000.00") and bill.insurance_coverage == Decimal("30000.00")
    assert bill.final_amount == Decimal("20000.00") and bill.amount_paid == 0 and bill.status == "PENDING"
    assert bill.balance_due == Decimal("20000.00")


def test_partial_payment_status_then_paid(app):
    p, d, admin = make_patient(), make_doctor("surgeon"), make_admin()
    make_policy(p, "80", "30000")
    bill = _bill_with_treatment(p, d, admin, "49999.99")
    payment_service.pay_bill(bill, "cash", "5000", {}, admin)
    assert bill.status == "PARTIALLY_PAID" and bill.balance_due == Decimal("15000.00")
    with pytest.raises(PaymentError, match="cannot exceed"):
        payment_service.pay_bill(bill, "cash", "15000.01", {}, admin)
    payment_service.pay_bill(bill, "upi", "15000", {"upi_id": "abc@bank"}, admin)
    assert bill.status == "PAID" and bill.balance_due == 0


def test_failed_bill_payment_changes_nothing(app):
    p, d, admin = make_patient(), make_doctor("surgeon"), make_admin()
    bill = _bill_with_treatment(p, d, admin, "1000", insured=False)
    txn = payment_service.pay_bill(bill, "upi", "500", {"upi_id": "a@fail"}, admin)
    assert txn.status == "failed" and bill.amount_paid == 0 and bill.status == "PENDING"


def test_insurer_settlement_is_separate_from_patient_payments(app):
    p, d, admin = make_patient(), make_doctor("surgeon"), make_admin()
    make_policy(p, "50", "100000")
    bill = _bill_with_treatment(p, d, admin, "999.99")
    paid_before = bill.amount_paid
    txn = payment_service.settle_insurer(bill, admin)
    assert txn.status == "success" and bill.insurer_settled and bill.amount_paid == paid_before
    assert txn.counts_toward_balance is False
    with pytest.raises(PaymentError, match="already"):
        payment_service.settle_insurer(bill, admin)


def test_prepaid_consultation_is_credited_on_the_bill(app):
    p, d, admin = make_patient(), make_doctor(), make_admin()
    appt = paid_appointment(p, d)
    bill = billing_service.create_bill(p, admin, False, [])
    assert bill.consultation_fee == appt.fee and bill.amount_paid == appt.fee and bill.status == "PAID"


def test_nothing_to_bill_is_an_error(app):
    with pytest.raises(billing_service.BillingError):
        billing_service.create_bill(make_patient(), make_admin(), True, [])


def test_treatment_cost_polymorphism(app):
    from app.models.treatment import (EmergencyTreatment, MedicineTreatment, PhysiotherapyTreatment, SurgeryTreatment)
    assert MedicineTreatment(medicine_charges=700, consultation_charges=300).calculate_cost() == Decimal("1000.00")
    assert SurgeryTreatment(operation_charges=10000, surgeon_charges=5000, hospital_charges=2500).calculate_cost() == Decimal("17500.00")
    assert PhysiotherapyTreatment(session_charges=400, sessions=6).calculate_cost() == Decimal("2400.00")
    assert EmergencyTreatment(emergency_charges=2000, treatment_charges=1500).calculate_cost() == Decimal("3500.00")


def test_doctor_fee_polymorphism_and_defaults(app):
    fees = {k: make_doctor(k).calculate_consultation_fee() for k in ("general", "cardiologist", "neurologist", "surgeon")}
    assert fees == {"general": 500, "cardiologist": 1500, "neurologist": 1800, "surgeon": 2500}
    d = make_doctor("general")
    assert d.calculate_consultation_fee(follow_up=True) == Decimal("400.00")
    d.specialization.base_fee = Decimal("650")         # fees are data, not hard-coded
    assert d.calculate_consultation_fee() == Decimal("650.00")


def test_charge_summary_add_magic_method():
    a, b = ChargeSummary(room_charges=1000), ChargeSummary(room_charges=500, medicine_charges=50)
    assert (a + b).total == Decimal("1550.00")


def test_patient_equality_and_str(app):
    p = make_patient()
    same = db.session.get(type(p), p.id)
    assert p == same and p != make_patient() and "PAT-" in str(p)
