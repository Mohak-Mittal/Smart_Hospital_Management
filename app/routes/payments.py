"""Simulated payment pages."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import PaymentForm
from app.models import Appointment, Bill, PaymentTransaction
from app.models.payment import DEMO_NOTICE
from app.routes import flash_form_errors
from app.services import payment_service
from app.services.access import user_can_view_bill
from app.services.payment_service import PaymentError
from app.utils.decorators import role_required

payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/appointment/<int:appt_id>", methods=["GET", "POST"])
@role_required("patient")
def pay_appointment(appt_id):
    appt = db.get_or_404(Appointment, appt_id)
    patient = current_user.patient_profile
    if patient is None or appt.patient_id != patient.id:
        abort(403)
    if appt.status != "pending":
        flash("This appointment is not waiting for payment.", "info")
        return redirect(url_for("patient.appointments", tab="all"))
    form = PaymentForm()
    if form.validate_on_submit():
        try:
            txn = payment_service.pay_appointment(appt, form.method.data, form.details(), current_user)
        except PaymentError as exc:
            flash(str(exc), "danger")
        else:
            if txn.status == "success":
                flash("Payment successful - your appointment is confirmed.", "success")
                return redirect(url_for("payments.receipt", txn_id=txn.id))
            flash(txn.message or "Payment failed. Nothing was charged. You can try again.", "danger")
    elif request.method == "POST":
        flash_form_errors(form)
    return render_template("patient/payment.html", form=form, appt=appt, amount=appt.fee, notice=DEMO_NOTICE,
                           title="Pay consultation fee",
                           cancel_url=url_for("patient.appointments", tab="pending"))


@payments_bp.route("/bill/<int:bill_id>", methods=["GET", "POST"])
@role_required("patient")
def pay_bill(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    if not user_can_view_bill(current_user, bill) or current_user.role != "patient":
        abort(403)
    if bill.balance_due <= 0:
        flash("This invoice has no balance due.", "info")
        return redirect(url_for("patient.invoices"))
    form = PaymentForm()
    if request.method == "GET":
        form.amount.data = bill.balance_due
    if form.validate_on_submit():
        try:
            txn = payment_service.pay_bill(bill, form.method.data, form.amount.data or bill.balance_due,
                                           form.details(), current_user)
        except PaymentError as exc:
            flash(str(exc), "danger")
        else:
            if txn.status == "success":
                flash("Payment recorded.", "success")
                return redirect(url_for("payments.receipt", txn_id=txn.id))
            flash(txn.message or "Payment failed. Nothing was charged.", "danger")
    elif request.method == "POST":
        flash_form_errors(form)
    return render_template("patient/payment.html", form=form, bill=bill, amount=bill.balance_due,
                           notice=DEMO_NOTICE, title=f"Pay invoice {bill.invoice_number}",
                           cancel_url=url_for("patient.invoices"), ask_amount=True)


@payments_bp.route("/receipt/<int:txn_id>")
@role_required("patient", "admin")
def receipt(txn_id):
    txn = db.get_or_404(PaymentTransaction, txn_id)
    if current_user.role == "patient" and (current_user.patient_profile is None
                                           or txn.patient_id != current_user.patient_profile.id):
        abort(403)
    return render_template("patient/receipt.html", txn=txn, notice=DEMO_NOTICE)
