"""Admin / reception portal.  The blueprint-wide guard below protects EVERY admin route."""
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from app.extensions import db, login_manager
from app.forms import (AdminPatientForm, AssignRoomForm, BillForm, DoctorForm, EmergencyForm, InsuranceForm,
                       MedicineForm, NurseAssignForm, NurseForm, PaymentForm, RoomForm, RoomTypeForm,
                       SpecializationForm, StockForm)
from app.models import (ActivityLog, Appointment, Bill, Discharge, Doctor, EmergencyCase, InsurancePolicy,
                        Medicine, Nurse, Patient, PaymentTransaction, Room, RoomAssignment, RoomType,
                        Specialization, StockMovement, User)
from app.models.activity import log_activity
from app.models.types import to_money
from app.routes import flash_form_errors, paginate
from app.services import (appointment_service, billing_service, discharge_service, emergency_service,
                          inventory_service, payment_service, room_service)
from app.services.appointment_service import BookingError
from app.services.billing_service import BillingError
from app.services.discharge_service import DischargeError
from app.services.emergency_service import EmergencyError
from app.services.inventory_service import InventoryError
from app.services.payment_service import PaymentError
from app.services.room_service import RoomError
from app.utils.id_generator import finalize_code, temp_code
from app.utils.timeutil import hospital_now

admin_bp = Blueprint("admin", __name__)


@admin_bp.before_request
def admin_only():
    """Runs before every route in this blueprint: must be a logged-in admin."""
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if current_user.role != "admin":
        abort(403)


def form_page(form, title, back, submit_label="Save", subtitle=None):
    return render_template("shared/form.html", form=form, title=title, back=back,
                           submit_label=submit_label, subtitle=subtitle)


def patient_choices(blank=None):
    rows = [(p.id, f"{p.patient_code} - {p.full_name}")
            for p in Patient.query.join(User, Patient.user_id == User.id).order_by(User.name)]
    return ([(0, blank)] if blank else []) + rows


# ------------------------------------------------------------------ dashboard
@admin_bp.route("/")
def dashboard():
    now = hospital_now()
    start = datetime.combine(now.date(), datetime.min.time())
    live = ("scheduled", "completed", "emergency")
    total_rooms = Room.query.filter_by(active=True).count()
    occupied = RoomAssignment.query.filter_by(released_at=None).count()
    pending_bills = Bill.query.filter(Bill.status != "PAID").all()
    status_counts = dict(db.session.query(Appointment.status, func.count()).group_by(Appointment.status).all())
    days = [now.date() - timedelta(days=i) for i in range(6, -1, -1)]
    revenue = []
    for day in days:
        s = datetime.combine(day, datetime.min.time())
        txns = PaymentTransaction.query.filter(
            PaymentTransaction.status == "success", PaymentTransaction.counts_toward_balance.is_(True),
            PaymentTransaction.created_at >= s, PaymentTransaction.created_at < s + timedelta(days=1)).all()
        revenue.append(float(sum((t.amount for t in txns), Decimal("0"))))
    stats = {
        "patients": Patient.query.count(), "doctors": Doctor.query.count(), "nurses": Nurse.query.count(),
        "today": Appointment.query.filter(Appointment.status.in_(live), Appointment.start_time >= start,
                                          Appointment.start_time < start + timedelta(days=1)).count(),
        "upcoming": Appointment.query.filter(Appointment.status == "scheduled",
                                             Appointment.start_time >= start + timedelta(days=1)).count(),
        "emergency": EmergencyCase.query.filter_by(status="waiting").count(),
        "rooms_total": total_rooms, "rooms_occupied": occupied, "rooms_free": max(total_rooms - occupied, 0),
        "pending_bills": len(pending_bills),
        "pending_amount": to_money(sum((b.balance_due for b in pending_bills), Decimal("0"))),
    }
    low = Medicine.query.filter(Medicine.active.is_(True), Medicine.quantity <= Medicine.reorder_level) \
        .order_by(Medicine.quantity).limit(8).all()
    activity = ActivityLog.query.order_by(ActivityLog.id.desc()).limit(10).all()
    chart = {"status_labels": [k.title() for k in status_counts], "status_values": list(status_counts.values()),
             "days": [d.strftime("%d %b") for d in days], "revenue": revenue}
    return render_template("admin/dashboard.html", stats=stats, low=low, activity=activity, chart=chart)


# ------------------------------------------------------------------ patients
@admin_bp.route("/patients")
def patients():
    q = request.args.get("q", "").strip()
    query = Patient.query.join(User, Patient.user_id == User.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), Patient.patient_code.ilike(like), User.email.ilike(like),
                                 Patient.phone.ilike(like)))
    page = paginate(query.order_by(Patient.id.desc()))
    return render_template("admin/patients.html", page=page, q=q, outstanding=billing_service.outstanding_for_patient)


@admin_bp.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
def edit_patient(patient_id):
    p = db.get_or_404(Patient, patient_id)
    form = AdminPatientForm(obj=p)
    if request.method == "GET":
        form.name.data, form.active.data, form.medical_history.data = p.full_name, p.user.active, p.medical_history
    if form.validate_on_submit():
        p.user.name, p.user.active = form.name.data.strip(), form.active.data
        p.phone, p.date_of_birth = form.phone.data or None, form.date_of_birth.data
        p.gender, p.blood_group = form.gender.data or None, form.blood_group.data or None
        p.address, p.emergency_contact = form.address.data or None, form.emergency_contact.data or None
        p.medical_history = form.medical_history.data
        log_activity(f"Patient {p.patient_code} record updated", current_user)
        db.session.commit()
        flash("Patient updated.", "success")
        return redirect(url_for("admin.patients"))
    return form_page(form, f"Edit patient {p.patient_code}", url_for("admin.patients"))


# ------------------------------------------------------------------ doctors
def _fill_doctor_form(form, doctor):
    form.name.data, form.active.data = doctor.full_name, doctor.user.active
    form.working_days.data = [str(d) for d in doctor.working_day_numbers]


def _save_doctor(form, doctor=None):
    """Create or update a doctor + their login.  Returns False if validation fails."""
    email = form.email.data.strip().lower()
    clash = User.query.filter(User.email == email, User.id != (doctor.user_id if doctor else 0)).first()
    if clash:
        form.email.errors = list(form.email.errors) + ["That email is already used."]
        return False
    if doctor is None and not form.password.data:
        form.password.errors = list(form.password.errors) + ["Password is required for a new doctor."]
        return False
    if doctor is None:
        user = User(email=email, name=form.name.data.strip(), role="doctor")
        doctor = Doctor(doctor_code=temp_code(), user=user, start_time=form.start_time.data,
                        end_time=form.end_time.data)
        db.session.add_all([user, doctor])
    user = doctor.user
    user.email, user.name, user.active = email, form.name.data.strip(), form.active.data
    if form.password.data:
        user.set_password(form.password.data)
    doctor.phone = form.phone.data or None
    doctor.specialization_id = form.specialization_id.data
    doctor.department, doctor.qualification = form.department.data or None, form.qualification.data or None
    doctor.experience_years, doctor.bio = form.experience_years.data or 0, form.bio.data or None
    doctor.fee_override = to_money(form.fee_override.data) if form.fee_override.data is not None else None
    doctor.working_days = ",".join(sorted(form.working_days.data))
    doctor.start_time, doctor.end_time = form.start_time.data, form.end_time.data
    doctor.slot_minutes = form.slot_minutes.data
    doctor.accepting_appointments = form.accepting_appointments.data
    db.session.flush()
    if doctor.doctor_code.startswith("TMP-"):
        finalize_code(doctor, "DOC", "doctor_code")
    log_activity(f"Doctor {doctor.doctor_code} saved", current_user)
    db.session.commit()
    return True


def _doctor_form(**kw):
    form = DoctorForm(**kw)
    form.specialization_id.choices = [(s.id, s.name) for s in Specialization.query.order_by(Specialization.name)]
    return form


@admin_bp.route("/doctors")
def doctors():
    q = request.args.get("q", "").strip()
    query = Doctor.query.join(User, Doctor.user_id == User.id).join(Specialization)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), Specialization.name.ilike(like), Doctor.doctor_code.ilike(like)))
    page = paginate(query.order_by(User.name))
    return render_template("admin/doctors.html", page=page, q=q,
                           specs=Specialization.query.order_by(Specialization.base_fee).all())


@admin_bp.route("/doctors/new", methods=["GET", "POST"])
def new_doctor():
    form = _doctor_form()
    if request.method == "GET":
        form.working_days.data = ["0", "1", "2", "3", "4"]
        form.start_time.data, form.end_time.data = datetime.strptime("09:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time()
    if form.validate_on_submit() and _save_doctor(form):
        flash("Doctor created.", "success")
        return redirect(url_for("admin.doctors"))
    return form_page(form, "Add doctor", url_for("admin.doctors"))


@admin_bp.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
def edit_doctor(doctor_id):
    d = db.get_or_404(Doctor, doctor_id)
    form = _doctor_form(obj=d)
    if request.method == "GET":
        _fill_doctor_form(form, d)
    if form.validate_on_submit() and _save_doctor(form, d):
        flash("Doctor updated.", "success")
        return redirect(url_for("admin.doctors"))
    return form_page(form, f"Edit {d.full_name}", url_for("admin.doctors"))


@admin_bp.route("/doctors/<int:doctor_id>/toggle", methods=["POST"])
def toggle_doctor(doctor_id):
    """Deactivate / reactivate the doctor's account (they stay in the records)."""
    d = db.get_or_404(Doctor, doctor_id)
    d.user.active = not d.user.active
    log_activity(f"Doctor {d.doctor_code} {'activated' if d.user.active else 'deactivated'}", current_user)
    db.session.commit()
    flash(f"{d.full_name} is now {'active' if d.user.active else 'inactive'}.", "success")
    return redirect(url_for("admin.doctors"))


@admin_bp.route("/doctors/<int:doctor_id>/availability", methods=["POST"])
def toggle_availability(doctor_id):
    d = db.get_or_404(Doctor, doctor_id)
    d.accepting_appointments = not d.accepting_appointments
    db.session.commit()
    flash(f"{d.full_name} is {'now accepting' if d.accepting_appointments else 'no longer accepting'} appointments.", "success")
    return redirect(url_for("admin.doctors"))


@admin_bp.route("/specializations/<int:spec_id>/edit", methods=["GET", "POST"])
def edit_specialization(spec_id):
    s = db.get_or_404(Specialization, spec_id)
    form = SpecializationForm(obj=s)
    if form.validate_on_submit():
        s.base_fee, s.description = to_money(form.base_fee.data), form.description.data or None
        log_activity(f"Fee for {s.name} changed", current_user)
        db.session.commit()
        flash("Consultation fee updated.", "success")
        return redirect(url_for("admin.doctors"))
    return form_page(form, f"Consultation fee - {s.name}", url_for("admin.doctors"))


# ------------------------------------------------------------------ nurses
def _save_nurse(form, nurse=None):
    email = form.email.data.strip().lower()
    if User.query.filter(User.email == email, User.id != (nurse.user_id if nurse else 0)).first():
        form.email.errors = list(form.email.errors) + ["That email is already used."]
        return False
    if nurse is None and not form.password.data:
        form.password.errors = list(form.password.errors) + ["Password is required for a new nurse."]
        return False
    if nurse is None:
        user = User(email=email, name=form.name.data.strip(), role="nurse")
        nurse = Nurse(nurse_code=temp_code(), user=user)
        db.session.add_all([user, nurse])
    user = nurse.user
    user.email, user.name, user.active = email, form.name.data.strip(), form.active.data
    if form.password.data:
        user.set_password(form.password.data)
    nurse.phone, nurse.ward, nurse.shift = form.phone.data or None, form.ward.data or None, form.shift.data
    db.session.flush()
    if nurse.nurse_code.startswith("TMP-"):
        finalize_code(nurse, "NUR", "nurse_code")
    log_activity(f"Nurse {nurse.nurse_code} saved", current_user)
    db.session.commit()
    return True


@admin_bp.route("/nurses")
def nurses():
    page = paginate(Nurse.query.join(User, Nurse.user_id == User.id).order_by(User.name))
    return render_template("admin/nurses.html", page=page)


@admin_bp.route("/nurses/new", methods=["GET", "POST"])
def new_nurse():
    form = NurseForm()
    if form.validate_on_submit() and _save_nurse(form):
        flash("Nurse created.", "success")
        return redirect(url_for("admin.nurses"))
    return form_page(form, "Add nurse", url_for("admin.nurses"))


@admin_bp.route("/nurses/<int:nurse_id>/edit", methods=["GET", "POST"])
def edit_nurse(nurse_id):
    n = db.get_or_404(Nurse, nurse_id)
    form = NurseForm(obj=n)
    if request.method == "GET":
        form.name.data, form.active.data = n.full_name, n.user.active
    if form.validate_on_submit() and _save_nurse(form, n):
        flash("Nurse updated.", "success")
        return redirect(url_for("admin.nurses"))
    return form_page(form, f"Edit {n.full_name}", url_for("admin.nurses"))


@admin_bp.route("/nurses/<int:nurse_id>/toggle", methods=["POST"])
def toggle_nurse(nurse_id):
    n = db.get_or_404(Nurse, nurse_id)
    n.user.active = not n.user.active
    db.session.commit()
    flash(f"{n.full_name} is now {'active' if n.user.active else 'inactive'}.", "success")
    return redirect(url_for("admin.nurses"))


@admin_bp.route("/nurses/<int:nurse_id>/patients", methods=["GET", "POST"])
def nurse_patients(nurse_id):
    n = db.get_or_404(Nurse, nurse_id)
    form = NurseAssignForm()
    form.patient_id.choices = patient_choices()
    if form.validate_on_submit():
        p = db.session.get(Patient, form.patient_id.data)
        if p is None:
            flash("Patient not found.", "danger")
        elif p in n.assigned_patients:
            flash("That patient is already assigned.", "info")
        else:
            n.assigned_patients.append(p)
            db.session.commit()
            flash("Patient assigned.", "success")
        return redirect(url_for("admin.nurse_patients", nurse_id=n.id))
    return render_template("admin/nurse_patients.html", nurse=n, form=form)


@admin_bp.route("/nurses/<int:nurse_id>/patients/<int:patient_id>/remove", methods=["POST"])
def nurse_unassign(nurse_id, patient_id):
    n = db.get_or_404(Nurse, nurse_id)
    p = db.get_or_404(Patient, patient_id)
    if p in n.assigned_patients:
        n.assigned_patients.remove(p)
        db.session.commit()
        flash("Patient removed from this nurse.", "success")
    return redirect(url_for("admin.nurse_patients", nurse_id=n.id))


# ------------------------------------------------------------------ appointments
@admin_bp.route("/appointments")
def appointments():
    q, status, day = request.args.get("q", "").strip(), request.args.get("status", ""), request.args.get("date", "")
    query = (Appointment.query.join(Patient, Appointment.patient_id == Patient.id)
             .join(User, Patient.user_id == User.id).join(Doctor, Appointment.doctor_id == Doctor.id))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), Patient.patient_code.ilike(like), Appointment.code.ilike(like)))
    if status in ("pending", "scheduled", "completed", "cancelled", "emergency"):
        query = query.filter(Appointment.status == status)
    if day:
        try:
            s = datetime.strptime(day, "%Y-%m-%d")
            query = query.filter(Appointment.start_time >= s, Appointment.start_time < s + timedelta(days=1))
        except ValueError:
            flash("Invalid date.", "warning")
    page = paginate(query.order_by(Appointment.start_time.desc()))
    return render_template("admin/appointments.html", page=page, q=q, status=status, day=day)


@admin_bp.route("/appointments/<int:appt_id>/cancel", methods=["POST"])
def cancel_appointment(appt_id):
    appt = db.get_or_404(Appointment, appt_id)
    try:
        refund = appointment_service.cancel_appointment(appt, by_admin=True, reason="Cancelled by admin")
        flash("Appointment cancelled." + (f" Demo refund ₹{refund:,.2f}." if refund else ""), "success")
    except BookingError as exc:
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("admin.appointments"))


@admin_bp.route("/appointments/<int:appt_id>/cash", methods=["POST"])
def appointment_cash(appt_id):
    """Reception collects the consultation fee in cash (demo receipt) for a pending booking."""
    appt = db.get_or_404(Appointment, appt_id)
    try:
        txn = payment_service.pay_appointment(appt, "cash", {}, current_user)
        flash(f"Cash received - receipt {txn.txn_ref}. Appointment confirmed.", "success")
    except PaymentError as exc:
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("admin.appointments"))


# ------------------------------------------------------------------ rooms
@admin_bp.route("/rooms")
def rooms():
    rooms_ = Room.query.order_by(Room.room_number).all()
    occupancy = {a.room_id: a for a in RoomAssignment.query.filter_by(released_at=None).all()}
    return render_template("admin/rooms.html", rooms=rooms_, occupancy=occupancy,
                           types=RoomType.query.order_by(RoomType.daily_rate).all(),
                           stay_days=room_service.stay_days, charge=room_service.calculate_room_charge)


def _room_form(**kw):
    form = RoomForm(**kw)
    form.room_type_id.choices = [(t.id, f"{t.name}") for t in RoomType.query.order_by(RoomType.daily_rate)]
    return form


@admin_bp.route("/rooms/new", methods=["GET", "POST"])
def new_room():
    form = _room_form()
    if form.validate_on_submit():
        if Room.query.filter_by(room_number=form.room_number.data.strip()).first():
            form.room_number.errors = list(form.room_number.errors) + ["Room number already exists."]
        else:
            db.session.add(Room(room_number=form.room_number.data.strip(), room_type_id=form.room_type_id.data,
                                floor=form.floor.data or None, active=form.active.data))
            db.session.commit()
            flash("Room added.", "success")
            return redirect(url_for("admin.rooms"))
    return form_page(form, "Add room", url_for("admin.rooms"))


@admin_bp.route("/rooms/<int:room_id>/edit", methods=["GET", "POST"])
def edit_room(room_id):
    r = db.get_or_404(Room, room_id)
    form = _room_form(obj=r)
    if form.validate_on_submit():
        clash = Room.query.filter(Room.room_number == form.room_number.data.strip(), Room.id != r.id).first()
        if clash:
            form.room_number.errors = list(form.room_number.errors) + ["Room number already exists."]
        elif r.is_occupied and not form.active.data:
            form.active.errors = list(form.active.errors) + ["Release the patient before taking the room out of service."]
        else:
            r.room_number, r.room_type_id = form.room_number.data.strip(), form.room_type_id.data
            r.floor, r.active = form.floor.data or None, form.active.data
            db.session.commit()
            flash("Room updated.", "success")
            return redirect(url_for("admin.rooms"))
    return form_page(form, f"Edit room {r.room_number}", url_for("admin.rooms"))


@admin_bp.route("/room-types/<int:type_id>/edit", methods=["GET", "POST"])
def edit_room_type(type_id):
    t = db.get_or_404(RoomType, type_id)
    form = RoomTypeForm(obj=t)
    if form.validate_on_submit():
        t.daily_rate = to_money(form.daily_rate.data)
        db.session.commit()
        flash("Daily rate updated.", "success")
        return redirect(url_for("admin.rooms"))
    return form_page(form, f"Daily rate - {t.name}", url_for("admin.rooms"))


@admin_bp.route("/rooms/<int:room_id>/assign", methods=["GET", "POST"])
def assign_room(room_id):
    r = db.get_or_404(Room, room_id)
    form = AssignRoomForm()
    form.patient_id.choices = patient_choices()
    if form.validate_on_submit():
        patient = db.session.get(Patient, form.patient_id.data)
        try:
            room_service.assign_room(r, patient, current_user)
            flash(f"{r} assigned to {patient.full_name}.", "success")
            return redirect(url_for("admin.rooms"))
        except RoomError as exc:
            flash(str(exc), "danger")
    return form_page(form, f"Assign {r}", url_for("admin.rooms"), "Assign room",
                     subtitle=f"{r.room_type.name} - ₹{r.room_type.daily_rate:,.2f} per day")


@admin_bp.route("/rooms/<int:room_id>/release", methods=["POST"])
def release_room(room_id):
    r = db.get_or_404(Room, room_id)
    assignment = r.current_assignment
    if assignment is None:
        flash("This room is not occupied.", "info")
    else:
        room_service.release_assignment(assignment, current_user)
        flash(f"Room {r.room_number} released.", "success")
    return redirect(url_for("admin.rooms"))


# ------------------------------------------------------------------ medicines
@admin_bp.route("/medicines")
def medicines():
    q, low = request.args.get("q", "").strip(), request.args.get("low") == "1"
    query = Medicine.query
    if q:
        query = query.filter(or_(Medicine.name.ilike(f"%{q}%"), Medicine.category.ilike(f"%{q}%"),
                                 Medicine.medicine_code.ilike(f"%{q}%")))
    if low:
        query = query.filter(Medicine.quantity <= Medicine.reorder_level)
    return render_template("admin/medicines.html", page=paginate(query.order_by(Medicine.name)), q=q, low=low)


@admin_bp.route("/medicines/new", methods=["GET", "POST"])
def new_medicine():
    form = MedicineForm()
    if form.validate_on_submit():
        m = Medicine(medicine_code=temp_code(), name=form.name.data.strip(), category=form.category.data.strip(),
                     price=to_money(form.price.data), quantity=0, reorder_level=form.reorder_level.data,
                     active=form.active.data)
        db.session.add(m)
        finalize_code(m, "MED", "medicine_code")
        if form.quantity.data:
            inventory_service.add_stock(m, form.quantity.data, "Opening stock", current_user, commit=False)
        db.session.commit()
        flash("Medicine added.", "success")
        return redirect(url_for("admin.medicines"))
    return form_page(form, "Add medicine", url_for("admin.medicines"))


@admin_bp.route("/medicines/<int:med_id>/edit", methods=["GET", "POST"])
def edit_medicine(med_id):
    m = db.get_or_404(Medicine, med_id)
    form = MedicineForm(obj=m)
    del form.quantity            # stock changes go through add/remove stock so they are logged
    if form.validate_on_submit():
        m.name, m.category = form.name.data.strip(), form.category.data.strip()
        m.price, m.reorder_level, m.active = to_money(form.price.data), form.reorder_level.data, form.active.data
        db.session.commit()
        flash("Medicine updated.", "success")
        return redirect(url_for("admin.medicines"))
    return form_page(form, f"Edit {m.name}", url_for("admin.medicines"))


def _stock_change(med_id, action):
    m = db.get_or_404(Medicine, med_id)
    form = StockForm()
    if form.validate_on_submit():
        try:
            fn = inventory_service.add_stock if action == "add" else inventory_service.remove_stock
            fn(m, form.quantity.data, form.reason.data or ("Stock received" if action == "add" else "Stock removed"),
               current_user)
            flash(f"Stock updated. {m.name}: {m.quantity} in stock.", "success")
            return redirect(url_for("admin.medicines"))
        except InventoryError as exc:
            form.quantity.errors = list(form.quantity.errors) + [str(exc)]
    return form_page(form, f"{'Add' if action == 'add' else 'Remove'} stock - {m.name}", url_for("admin.medicines"),
                     "Update stock", subtitle=f"Currently {m.quantity} in stock")


@admin_bp.route("/medicines/<int:med_id>/stock/add", methods=["GET", "POST"])
def add_stock(med_id):
    return _stock_change(med_id, "add")


@admin_bp.route("/medicines/<int:med_id>/stock/remove", methods=["GET", "POST"])
def remove_stock(med_id):
    return _stock_change(med_id, "remove")


@admin_bp.route("/medicines/<int:med_id>/movements")
def movements(med_id):
    m = db.get_or_404(Medicine, med_id)
    page = paginate(m.movements.order_by(StockMovement.id.desc()))
    return render_template("admin/movements.html", med=m, page=page)


# ------------------------------------------------------------------ emergency
@admin_bp.route("/emergency")
def emergency():
    waiting = emergency_service.waiting_queue()
    active = EmergencyCase.query.filter_by(status="in_treatment").order_by(EmergencyCase.arrived_at).all()
    recent = EmergencyCase.query.filter_by(status="resolved").order_by(EmergencyCase.id.desc()).limit(8).all()
    doctors_ = Doctor.query.join(User, Doctor.user_id == User.id).filter(User.active.is_(True)).order_by(User.name).all()
    return render_template("admin/emergency.html", waiting=waiting, active=active, recent=recent, doctors=doctors_)


@admin_bp.route("/emergency/new", methods=["GET", "POST"])
def new_emergency():
    form = EmergencyForm()
    form.patient_id.choices = patient_choices("Walk-in / not registered")
    if form.validate_on_submit():
        patient = db.session.get(Patient, form.patient_id.data) if form.patient_id.data else None
        try:
            emergency_service.add_case(form.patient_name.data, form.complaint.data, form.priority.data, patient,
                                       form.age.data, current_user)
            flash("Emergency case added to the queue.", "success")
            return redirect(url_for("admin.emergency"))
        except EmergencyError as exc:
            flash(str(exc), "danger")
    return form_page(form, "Add emergency case", url_for("admin.emergency"), "Add to queue")


@admin_bp.route("/emergency/<int:case_id>/priority", methods=["POST"])
def emergency_priority(case_id):
    case = db.get_or_404(EmergencyCase, case_id)
    try:
        emergency_service.set_priority(case, request.form.get("priority", type=int) or 0, current_user)
        flash("Priority updated.", "success")
    except EmergencyError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.emergency"))


@admin_bp.route("/emergency/<int:case_id>/status", methods=["POST"])
def emergency_status(case_id):
    case = db.get_or_404(EmergencyCase, case_id)
    try:
        emergency_service.set_status(case, request.form.get("status", ""), current_user)
        flash("Status updated.", "success")
    except EmergencyError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.emergency"))


@admin_bp.route("/emergency/<int:case_id>/assign", methods=["POST"])
def emergency_assign(case_id):
    case = db.get_or_404(EmergencyCase, case_id)
    doctor = db.session.get(Doctor, request.form.get("doctor_id", type=int) or 0)
    if doctor is None:
        flash("Choose a doctor.", "danger")
    else:
        try:
            emergency_service.assign_doctor(case, doctor, current_user)
            flash(f"Case assigned to Dr. {doctor.full_name}.", "success")
        except EmergencyError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("admin.emergency"))


# ------------------------------------------------------------------ billing
@admin_bp.route("/billing")
def billing():
    status, q = request.args.get("status", ""), request.args.get("q", "").strip()
    query = Bill.query.join(Patient, Bill.patient_id == Patient.id).join(User, Patient.user_id == User.id)
    if status in ("PENDING", "PARTIALLY_PAID", "PAID"):
        query = query.filter(Bill.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), Bill.invoice_number.ilike(like), Patient.patient_code.ilike(like)))
    return render_template("admin/billing.html", page=paginate(query.order_by(Bill.id.desc())), status=status, q=q)


@admin_bp.route("/billing/new", methods=["GET", "POST"])
def new_bill():
    form = BillForm()
    form.patient_id.choices = patient_choices()
    meds = [(0, "- none -")] + [(m.id, f"{m.name} ({m.quantity} in stock, ₹{m.price:,.2f})")
                                for m in Medicine.query.filter(Medicine.active.is_(True), Medicine.quantity > 0).order_by(Medicine.name)]
    for i in (1, 2, 3):
        getattr(form, f"medicine_{i}").choices = meds
    if form.validate_on_submit():
        patient = db.session.get(Patient, form.patient_id.data)
        items = []
        for i in (1, 2, 3):
            med_id, qty = getattr(form, f"medicine_{i}").data, getattr(form, f"qty_{i}").data
            if med_id:
                if not qty:
                    flash(f"Enter a quantity for pharmacy item {i}.", "danger")
                    return form_page(form, "Generate bill", url_for("admin.billing"), "Generate bill")
                items.append((db.session.get(Medicine, med_id), qty))
        try:
            bill = billing_service.create_bill(patient, current_user, form.apply_insurance.data, items, form.notes.data)
            flash(f"Bill {bill.invoice_number} generated.", "success")
            return redirect(url_for("admin.bill_detail", bill_id=bill.id))
        except (BillingError, InventoryError) as exc:
            flash(str(exc), "danger")
    return form_page(form, "Generate bill", url_for("admin.billing"), "Generate bill",
                     subtitle="Collects the patient's unbilled paid consultations, treatments, room stays "
                              "and any pharmacy items you add below.")


@admin_bp.route("/billing/<int:bill_id>")
def bill_detail(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    form = PaymentForm()
    form.amount.data = bill.balance_due
    return render_template("admin/bill_detail.html", bill=bill, form=form,
                           payments=bill.payments.order_by(PaymentTransaction.id.desc()).all())


@admin_bp.route("/billing/<int:bill_id>/pay", methods=["POST"])
def bill_pay(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    form = PaymentForm()
    if form.validate_on_submit():
        try:
            txn = payment_service.pay_bill(bill, form.method.data, form.amount.data or bill.balance_due,
                                           form.details(), current_user)
            flash("Payment recorded." if txn.status == "success" else (txn.message or "Payment failed."),
                  "success" if txn.status == "success" else "danger")
        except PaymentError as exc:
            flash(str(exc), "danger")
    else:
        flash_form_errors(form)
    return redirect(url_for("admin.bill_detail", bill_id=bill.id))


@admin_bp.route("/billing/<int:bill_id>/settle-insurer", methods=["POST"])
def bill_settle(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    try:
        txn = payment_service.settle_insurer(bill, current_user)
        flash("Insurer share settled." if txn.status == "success" else (txn.message or "Settlement failed."),
              "success" if txn.status == "success" else "danger")
    except PaymentError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.bill_detail", bill_id=bill.id))


# ------------------------------------------------------------------ insurance
@admin_bp.route("/insurance")
def insurance():
    q = request.args.get("q", "").strip()
    query = InsurancePolicy.query.join(Patient, InsurancePolicy.patient_id == Patient.id).join(User, Patient.user_id == User.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), InsurancePolicy.policy_number.ilike(like),
                                 InsurancePolicy.company_name.ilike(like)))
    return render_template("admin/insurance.html", page=paginate(query.order_by(InsurancePolicy.id.desc())), q=q,
                           today=hospital_now().date())


def _policy_save(form, policy=None):
    number = form.policy_number.data.strip()
    if InsurancePolicy.query.filter(InsurancePolicy.policy_number == number,
                                    InsurancePolicy.id != (policy.id if policy else 0)).first():
        form.policy_number.errors = list(form.policy_number.errors) + ["This policy number already exists."]
        return False
    policy = policy or InsurancePolicy()
    policy.patient_id, policy.policy_number = form.patient_id.data, number
    policy.company_name = form.company_name.data.strip()
    policy.coverage_percent, policy.max_coverage = to_money(form.coverage_percent.data), to_money(form.max_coverage.data)
    policy.status, policy.valid_until = form.status.data, form.valid_until.data
    db.session.add(policy)
    log_activity("Insurance policy saved", current_user)
    db.session.commit()
    return True


@admin_bp.route("/insurance/new", methods=["GET", "POST"])
def new_policy():
    form = InsuranceForm()
    form.patient_id.choices = patient_choices()
    if form.validate_on_submit() and _policy_save(form):
        flash("Policy saved.", "success")
        return redirect(url_for("admin.insurance"))
    return form_page(form, "Add insurance policy", url_for("admin.insurance"))


@admin_bp.route("/insurance/<int:policy_id>/edit", methods=["GET", "POST"])
def edit_policy(policy_id):
    p = db.get_or_404(InsurancePolicy, policy_id)
    form = InsuranceForm(obj=p)
    form.patient_id.choices = patient_choices()
    if form.validate_on_submit() and _policy_save(form, p):
        flash("Policy updated.", "success")
        return redirect(url_for("admin.insurance"))
    return form_page(form, f"Edit policy {p.masked_number}", url_for("admin.insurance"))


# ------------------------------------------------------------------ discharge
@admin_bp.route("/discharges")
def discharges():
    rows = [(p, discharge_service.evaluate(p)) for p in discharge_service.candidates()]
    history = Discharge.query.order_by(Discharge.id.desc()).limit(15).all()
    return render_template("admin/discharges.html", rows=rows, history=history)


@admin_bp.route("/discharges/<int:patient_id>", methods=["POST"])
def discharge(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    try:
        discharge_service.discharge_patient(patient, current_user, request.form.get("notes", ""))
        flash(f"{patient.full_name} has been discharged and any room released.", "success")
    except DischargeError as exc:
        flash("Discharge denied. Unmet conditions: " + "; ".join(exc.unmet), "danger")
    return redirect(url_for("admin.discharges"))
