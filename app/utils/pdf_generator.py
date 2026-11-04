"""PDF invoices and medical reports (ReportLab).

All user-provided text goes through escape() because ReportLab Paragraphs
understand a small HTML-like markup.  A DejaVu font is bundled so the rupee
sign (₹) prints correctly; if it is missing we fall back to "Rs.".
"""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
NAVY, TEAL, GREY = colors.HexColor("#0b2a4a"), colors.HexColor("#0f9d9a"), colors.HexColor("#5b6b7c")
_fonts = {}


def _fonts_ready():
    """Register fonts once.  Returns (regular, bold, rupee_symbol)."""
    if not _fonts:
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                          italic="DejaVu", boldItalic="DejaVu-Bold")
            _fonts.update(regular="DejaVu", bold="DejaVu-Bold", rupee="₹")
        except Exception:  # pragma: no cover - font file missing
            _fonts.update(regular="Helvetica", bold="Helvetica-Bold", rupee="Rs. ")
    return _fonts["regular"], _fonts["bold"], _fonts["rupee"]


def _styles():
    reg, bold, _ = _fonts_ready()
    return {
        "title": ParagraphStyle("t", fontName=bold, fontSize=18, textColor=NAVY, leading=22),
        "h": ParagraphStyle("h", fontName=bold, fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", fontName=reg, fontSize=9.5, leading=13),
        "small": ParagraphStyle("s", fontName=reg, fontSize=8, textColor=GREY, leading=11),
        "right": ParagraphStyle("r", fontName=reg, fontSize=9.5, alignment=2),
    }


def _money(value):
    return f"{_fonts_ready()[2]}{value:,.2f}"


def _multiline(text, style):
    """Convert plain text with line breaks into escaped paragraphs."""
    parts = [escape(line) for line in (text or "").splitlines()]
    return [Paragraph(p or "&nbsp;", style) for p in parts]


def _footer_factory(hospital_name):
    reg = _fonts_ready()[0]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(reg, 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, f"{hospital_name} - DEMO SYSTEM. Not a real medical or financial document.")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return footer


def build_invoice_pdf(bill, hospital_name: str) -> bytes:
    reg, bold, _ = _fonts_ready()
    s = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=f"Invoice {bill.invoice_number}")
    patient = bill.patient
    story = [Paragraph(escape(hospital_name), s["title"]),
             Paragraph("Smart Hospital Management &amp; Emergency Response System - DEMO", s["small"]),
             Spacer(1, 6)]
    head = Table([
        [Paragraph(f"<b>INVOICE</b> {escape(bill.invoice_number)}", s["p"]),
         Paragraph(f"Date: {bill.created_at:%d %b %Y}", s["right"])],
        [Paragraph(f"<b>Patient:</b> {escape(patient.full_name)} ({escape(patient.patient_code)})", s["p"]),
         Paragraph(f"Status: <b>{bill.status.replace('_', ' ')}</b>", s["right"])],
        [Paragraph(f"Phone: {escape(patient.phone or '-')}", s["p"]), ""],
    ], colWidths=[110 * mm, 64 * mm])
    head.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1, TEAL), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [head, Spacer(1, 8)]

    rows = [["Category", "Description", "Qty", "Unit price", "Amount"]]
    for it in bill.items:
        rows.append([it.category.title(), Paragraph(escape(it.description), s["p"]), str(it.quantity),
                     _money(it.unit_price), _money(it.amount)])
    table = Table(rows, colWidths=[24 * mm, 80 * mm, 12 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), reg),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6f9")]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, GREY)]))
    story += [table, Spacer(1, 8)]

    totals = [["Consultation", _money(bill.consultation_fee)], ["Treatment", _money(bill.treatment_charges)],
              ["Medicine", _money(bill.medicine_charges)], ["Room", _money(bill.room_charges)],
              ["Emergency", _money(bill.emergency_charges)], ["Subtotal", _money(bill.subtotal)]]
    if bill.insurance_coverage > 0:
        company = bill.policy.company_name if bill.policy else "Insurer"
        totals.append([f"Less: insurance coverage ({escape(company)})", "- " + _money(bill.insurance_coverage)])
    totals += [["Patient share (final amount)", _money(bill.final_amount)],
               ["Amount paid", _money(bill.amount_paid)], ["Outstanding balance", _money(bill.balance_due)]]
    tt = Table(totals, colWidths=[130 * mm, 44 * mm])
    tt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), reg), ("FONTNAME", (0, 5), (-1, 5), bold),
                            ("FONTNAME", (0, -3), (-1, -1), bold), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -3), (-1, -3), 0.8, NAVY),
                            ("TEXTCOLOR", (0, -1), (-1, -1), TEAL)]))
    story.append(tt)

    paid = [t for t in bill.payments if t.status == "success" and t.counts_toward_balance]
    if paid:
        story += [Paragraph("Payments received", s["h"])]
        for t in paid:
            story.append(Paragraph(f"{t.created_at:%d %b %Y %H:%M} - {t.method.upper()} - {escape(t.detail or '')}"
                                   f" - {_money(t.amount)} (ref {escape(t.txn_ref)})", s["p"]))
    story += [Spacer(1, 10), Paragraph("DEMO PAYMENT — NO REAL MONEY IS CHARGED. This invoice is sample data.", s["small"])]
    footer = _footer_factory(hospital_name)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def build_report_pdf(report, hospital_name: str) -> bytes:
    s = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=report.title)
    patient, doctor = report.patient, report.doctor
    story = [Paragraph(escape(hospital_name), s["title"]),
             Paragraph("MEDICAL REPORT - DEMO DATA, NOT REAL CLINICAL ADVICE", s["small"]), Spacer(1, 8),
             Paragraph(escape(report.title), s["h"])]
    meta = Table([
        [Paragraph(f"<b>Patient:</b> {escape(patient.full_name)} ({escape(patient.patient_code)})", s["p"]),
         Paragraph(f"<b>Report:</b> {escape(report.report_code)}", s["p"])],
        [Paragraph(f"<b>Doctor:</b> Dr. {escape(doctor.full_name)} ({escape(doctor.specialization.name)})", s["p"]),
         Paragraph(f"<b>Date:</b> {report.created_at:%d %b %Y}", s["p"])],
        [Paragraph(f"<b>Status:</b> {report.status.title()}", s["p"]),
         Paragraph(f"<b>Published:</b> {report.published_at:%d %b %Y}" if report.published_at else "", s["p"])],
    ], colWidths=[100 * mm, 74 * mm])
    meta.setStyle(TableStyle([("LINEBELOW", (0, -1), (-1, -1), 1, TEAL)]))
    story += [meta, Spacer(1, 8)] + _multiline(report.content, s["p"])
    footer = _footer_factory(hospital_name)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
