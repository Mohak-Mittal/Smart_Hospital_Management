"""Printable invoices and PDF downloads (invoice + medical report)."""
from io import BytesIO

from flask import Blueprint, abort, current_app, render_template, send_file
from flask_login import current_user

from app.extensions import db
from app.models import Bill, MedicalReport
from app.services.access import user_can_view_bill, user_can_view_report
from app.utils.decorators import role_required
from app.utils.pdf_generator import build_invoice_pdf, build_report_pdf

reports_bp = Blueprint("reports", __name__)


def _bill_or_403(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    if not user_can_view_bill(current_user, bill):
        abort(403)
    return bill


@reports_bp.route("/invoice/<int:bill_id>")
@role_required("patient", "admin")
def invoice_view(bill_id):
    """Printable HTML invoice (fallback to the PDF)."""
    return render_template("shared/invoice_print.html", bill=_bill_or_403(bill_id))


@reports_bp.route("/invoice/<int:bill_id>.pdf")
@role_required("patient", "admin")
def invoice_pdf(bill_id):
    bill = _bill_or_403(bill_id)
    data = build_invoice_pdf(bill, current_app.config["HOSPITAL_NAME"])
    return send_file(BytesIO(data), mimetype="application/pdf", as_attachment=True,
                     download_name=f"{bill.invoice_number}.pdf")


@reports_bp.route("/report/<int:report_id>.pdf")
@role_required("patient", "doctor", "admin")
def report_pdf(report_id):
    report = db.get_or_404(MedicalReport, report_id)
    if not user_can_view_report(current_user, report):
        abort(403)
    data = build_report_pdf(report, current_app.config["HOSPITAL_NAME"])
    return send_file(BytesIO(data), mimetype="application/pdf", as_attachment=True,
                     download_name=f"{report.report_code}.pdf")
