import pytest

from app.extensions import db
from app.models import Appointment, PaymentTransaction
from app.services import appointment_service, payment_service
from app.services.payment_service import PaymentError
from tests.factories import GOOD_CARD, free_slot, make_admin, make_doctor, make_patient, paid_appointment


def _pending(p=None, d=None):
    p, d = p or make_patient(), d or make_doctor()
    return p, d, appointment_service.book_appointment(p, d, free_slot(d))


def test_payment_success_confirms_booking(app):
    p, d, appt = _pending()
    txn = payment_service.pay_appointment(appt, "upi", {"upi_id": "me@bank"}, p.user)
    assert txn.status == "success" and appt.status == "scheduled" and appt.payment_status == "paid"
    assert txn.txn_ref.startswith("TXN-")


def test_payment_failure_leaves_booking_unconfirmed(app):
    p, d, appt = _pending()
    txn = payment_service.pay_appointment(appt, "upi", {"upi_id": "me@fail"}, p.user)
    assert txn.status == "failed" and appt.status == "pending" and appt.payment_status == "pending"
    txn = payment_service.pay_appointment(appt, "card", {**GOOD_CARD, "card_number": "4000000000000002"}, p.user)
    assert txn.status == "failed" and appt.status == "pending"
    # retry with a good card works
    assert payment_service.pay_appointment(appt, "card", GOOD_CARD, p.user).status == "success"


@pytest.mark.parametrize("bad", [{"card_number": "1234 5678 9012 3456"}, {"card_expiry": "01/20"},
                                 {"card_cvv": "12"}, {"card_name": ""}])
def test_invalid_card_details_fail(app, bad):
    p, d, appt = _pending()
    txn = payment_service.pay_appointment(appt, "card", {**GOOD_CARD, **bad}, p.user)
    assert txn.status == "failed" and appt.payment_status == "pending"


def test_full_card_number_and_cvv_never_stored(app):
    p, d, appt = _pending()
    payment_service.pay_appointment(appt, "card", GOOD_CARD, p.user)
    txn = PaymentTransaction.query.one()
    blob = " ".join(str(v) for v in (txn.detail, txn.message, txn.txn_ref))
    assert "4242424242424242" not in blob.replace(" ", "") and "****4242" in txn.detail and "123" not in txn.detail


def test_invalid_payment_method_rejected(app):
    p, d, appt = _pending()
    with pytest.raises(PaymentError, match="Unsupported"):
        payment_service.pay_appointment(appt, "bitcoin", {}, p.user)
    with pytest.raises(PaymentError, match="Unsupported"):
        payment_service.build_payment("cheque", 100)
    assert appt.payment_status == "pending"


def test_invalid_method_via_route_is_rejected(app, login_as):
    p, d, appt = _pending()
    c = login_as(p.user)
    resp = c.post(f"/payments/appointment/{appt.id}", data={"method": "bitcoin"})
    assert resp.status_code == 200
    assert db.session.get(Appointment, appt.id).payment_status == "pending"


def test_patient_cannot_mark_own_payment_as_paid(app, login_as):
    p, d, appt = _pending()
    c = login_as(p.user)
    # 1) admin-only endpoints are forbidden
    assert c.post(f"/admin/appointments/{appt.id}/cash").status_code == 403
    # 2) tampered form fields are ignored; a failing payment does not confirm anything
    c.post(f"/payments/appointment/{appt.id}", data={"method": "upi", "upi_id": "x@fail", "payment_status": "paid", "status": "scheduled"})
    db.session.expire_all()
    a = db.session.get(Appointment, appt.id)
    assert a.payment_status == "pending" and a.status == "pending"
    # 3) patients cannot complete appointments either
    assert c.post(f"/doctor/appointments/{appt.id}/complete").status_code == 403


def test_demo_banner_is_visible_on_payment_page(app, login_as):
    p, d, appt = _pending()
    html = login_as(p.user).get(f"/payments/appointment/{appt.id}").data
    assert b"NO REAL MONEY IS CHARGED" in html


def test_cannot_pay_someone_elses_appointment(app, login_as):
    p1, d, appt = _pending()
    assert login_as(make_patient().user).get(f"/payments/appointment/{appt.id}").status_code == 403


def test_cash_payment_issues_receipt(app):
    p, d, appt = _pending()
    txn = payment_service.pay_appointment(appt, "cash", {}, make_admin())
    assert txn.status == "success" and "Cash" in txn.detail
