"""WTForms classes: CSRF protection + server-side validation for every form."""
from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, DecimalField, IntegerField, PasswordField, SelectField,
                     SelectMultipleField, StringField, SubmitField, TextAreaField, TimeField)
from wtforms.validators import (DataRequired, Email, EqualTo, InputRequired, Length, NumberRange,
                                Optional, ValidationError)

from app.models.doctor import WEEKDAYS
from app.models.patient import BLOOD_GROUPS, GENDERS
from app.models.treatment import TREATMENT_CHOICES
from app.utils.validators import is_valid_phone, password_problems


def _phone(form, field):
    if field.data and not is_valid_phone(field.data):
        raise ValidationError("Enter a valid phone number (digits, optional +, spaces or dashes).")


def _password(form, field):
    problems = password_problems(field.data)
    if problems:
        raise ValidationError("Password needs " + ", ".join(problems) + ".")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), _phone])
    date_of_birth = DateField("Date of birth", validators=[Optional()])
    gender = SelectField("Gender", choices=[(g, g or "Select...") for g in GENDERS], validators=[Optional()])
    password = PasswordField("Password", validators=[DataRequired(), _password])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", "Passwords do not match.")])
    submit = SubmitField("Create account")


class ChangePasswordForm(FlaskForm):
    current = PasswordField("Current password", validators=[DataRequired()])
    password = PasswordField("New password", validators=[DataRequired(), _password])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("password", "Passwords do not match.")])
    submit = SubmitField("Change password")


class PatientProfileForm(FlaskForm):
    phone = StringField("Phone", validators=[Optional(), _phone])
    date_of_birth = DateField("Date of birth", validators=[Optional()])
    gender = SelectField("Gender", choices=[(g, g or "Select...") for g in GENDERS])
    blood_group = SelectField("Blood group", choices=[(g, g or "Select...") for g in BLOOD_GROUPS])
    address = StringField("Address", validators=[Optional(), Length(max=255)])
    emergency_contact = StringField("Emergency contact", validators=[Optional(), Length(max=120)])
    medical_history = TextAreaField("Medical history (self-reported, demo)", validators=[Optional(), Length(max=4000)])
    submit = SubmitField("Save profile")


class AdminPatientForm(PatientProfileForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    active = BooleanField("Account active", default=True)


class PaymentForm(FlaskForm):
    """Demo payment details.  Card number/CVV are validated in memory and never saved."""
    method = SelectField("Payment method", choices=[("upi", "UPI"), ("card", "Card"), ("cash", "Cash (receipt)")],
                         validators=[DataRequired()])
    amount = DecimalField("Amount (₹)", places=2, validators=[Optional(), NumberRange(min=0.01)])
    upi_id = StringField("UPI ID", validators=[Optional(), Length(max=80)], render_kw={"placeholder": "name@bank"})
    card_name = StringField("Name on card", validators=[Optional(), Length(max=80)])
    card_number = StringField("Card number", validators=[Optional(), Length(max=25)],
                              render_kw={"placeholder": "4242 4242 4242 4242", "autocomplete": "off"})
    card_expiry = StringField("Expiry (MM/YY)", validators=[Optional(), Length(max=7)])
    card_cvv = PasswordField("CVV", validators=[Optional(), Length(max=4)], render_kw={"autocomplete": "off"})
    submit = SubmitField("Pay (demo)")

    def details(self):
        return {"upi_id": self.upi_id.data, "card_name": self.card_name.data,
                "card_number": self.card_number.data, "card_expiry": self.card_expiry.data,
                "card_cvv": self.card_cvv.data}


class ConsultationForm(FlaskForm):
    diagnosis = StringField("Diagnosis (demo)", validators=[DataRequired(), Length(max=255)])
    notes = TextAreaField("Consultation notes", validators=[DataRequired(), Length(max=4000)])
    submit = SubmitField("Save consultation")


class TreatmentForm(FlaskForm):
    treatment_type = SelectField("Treatment type", choices=TREATMENT_CHOICES)
    diagnosis = StringField("Diagnosis", validators=[DataRequired(), Length(max=255)])
    plan_details = TextAreaField("Treatment plan", validators=[Optional(), Length(max=4000)])
    medicine_charges = DecimalField("Medicine charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    consultation_charges = DecimalField("Consultation charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    operation_charges = DecimalField("Operation charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    surgeon_charges = DecimalField("Surgeon charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    hospital_charges = DecimalField("Hospital charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    session_charges = DecimalField("Charge per session (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    sessions = IntegerField("Number of sessions", default=0, validators=[Optional(), NumberRange(min=0, max=200)])
    emergency_charges = DecimalField("Emergency charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    treatment_charges = DecimalField("Treatment charges (₹)", places=2, default=0, validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField("Create treatment plan")


class ProgressForm(FlaskForm):
    kind = SelectField("Entry type", choices=[("progress", "Progress note"), ("medication", "Medication / treatment entry")])
    note = TextAreaField("Note", validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField("Add entry")


class ReportForm(FlaskForm):
    title = StringField("Report title", validators=[DataRequired(), Length(max=160)])
    content = TextAreaField("Report content (demo data)", validators=[DataRequired(), Length(max=8000)], render_kw={"rows": 8})
    submit = SubmitField("Save draft")


class DoctorForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password (leave blank to keep current)", validators=[Optional(), _password])
    phone = StringField("Phone", validators=[Optional(), _phone])
    specialization_id = SelectField("Specialization", coerce=int)
    department = StringField("Department", validators=[Optional(), Length(max=80)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=120)])
    experience_years = IntegerField("Experience (years)", default=0, validators=[Optional(), NumberRange(min=0, max=70)])
    bio = TextAreaField("Short bio", validators=[Optional(), Length(max=500)])
    fee_override = DecimalField("Custom fee (₹) - blank = specialization fee", places=2, validators=[Optional(), NumberRange(min=0)])
    working_days = SelectMultipleField("Working days", choices=[(str(i), d) for i, d in enumerate(WEEKDAYS)])
    start_time = TimeField("Start time", validators=[InputRequired()])
    end_time = TimeField("End time", validators=[InputRequired()])
    slot_minutes = IntegerField("Slot length (minutes)", default=30, validators=[InputRequired(), NumberRange(min=10, max=120)])
    accepting_appointments = BooleanField("Accepting appointments", default=True)
    active = BooleanField("Account active", default=True)
    submit = SubmitField("Save doctor")

    def validate_end_time(self, field):
        if self.start_time.data and field.data and field.data <= self.start_time.data:
            raise ValidationError("End time must be after start time.")

    def validate_working_days(self, field):
        if not field.data:
            raise ValidationError("Choose at least one working day.")


class SpecializationForm(FlaskForm):
    base_fee = DecimalField("Base consultation fee (₹)", places=2, validators=[InputRequired(), NumberRange(min=0)])
    description = StringField("Description", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save fee")


class NurseForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password (leave blank to keep current)", validators=[Optional(), _password])
    phone = StringField("Phone", validators=[Optional(), _phone])
    ward = StringField("Ward", validators=[Optional(), Length(max=80)])
    shift = SelectField("Shift", choices=[("Day", "Day"), ("Evening", "Evening"), ("Night", "Night")])
    active = BooleanField("Account active", default=True)
    submit = SubmitField("Save nurse")


class NurseAssignForm(FlaskForm):
    patient_id = SelectField("Patient", coerce=int)
    submit = SubmitField("Assign patient")


class RoomForm(FlaskForm):
    room_number = StringField("Room number", validators=[DataRequired(), Length(max=20)])
    room_type_id = SelectField("Room type", coerce=int)
    floor = StringField("Floor", validators=[Optional(), Length(max=20)])
    active = BooleanField("In service", default=True)
    submit = SubmitField("Save room")


class RoomTypeForm(FlaskForm):
    daily_rate = DecimalField("Daily rate (₹)", places=2, validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField("Save rate")


class AssignRoomForm(FlaskForm):
    patient_id = SelectField("Patient", coerce=int)
    submit = SubmitField("Assign room")


class MedicineForm(FlaskForm):
    name = StringField("Medicine name", validators=[DataRequired(), Length(max=120)])
    category = StringField("Category", validators=[DataRequired(), Length(max=60)])
    price = DecimalField("Price per unit (₹)", places=2, validators=[InputRequired(), NumberRange(min=0)])
    quantity = IntegerField("Opening quantity", default=0, validators=[InputRequired(), NumberRange(min=0, max=1000000)])
    reorder_level = IntegerField("Reorder level", default=10, validators=[InputRequired(), NumberRange(min=0, max=100000)])
    active = BooleanField("Active", default=True)
    submit = SubmitField("Save medicine")


class StockForm(FlaskForm):
    quantity = IntegerField("Quantity", validators=[InputRequired(), NumberRange(min=1, max=1000000)])
    reason = StringField("Reason", validators=[Optional(), Length(max=120)])
    submit = SubmitField("Update stock")


class EmergencyForm(FlaskForm):
    patient_id = SelectField("Registered patient (optional)", coerce=int)
    patient_name = StringField("Name (for walk-in patients)", validators=[Optional(), Length(max=120)])
    age = IntegerField("Age", validators=[Optional(), NumberRange(min=0, max=130)])
    complaint = StringField("Complaint", validators=[DataRequired(), Length(max=255)])
    priority = SelectField("Priority", coerce=int,
                           choices=[(1, "1 - Critical"), (2, "2 - Serious"), (3, "3 - Moderate"), (4, "4 - Minor")])
    submit = SubmitField("Add to queue")


class BillForm(FlaskForm):
    patient_id = SelectField("Patient", coerce=int)
    apply_insurance = BooleanField("Apply insurance coverage", default=True)
    medicine_1 = SelectField("Pharmacy item 1", coerce=int)
    qty_1 = IntegerField("Qty", validators=[Optional(), NumberRange(min=1, max=10000)])
    medicine_2 = SelectField("Pharmacy item 2", coerce=int)
    qty_2 = IntegerField("Qty", validators=[Optional(), NumberRange(min=1, max=10000)])
    medicine_3 = SelectField("Pharmacy item 3", coerce=int)
    qty_3 = IntegerField("Qty", validators=[Optional(), NumberRange(min=1, max=10000)])
    notes = StringField("Notes", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Generate bill")


class InsuranceForm(FlaskForm):
    patient_id = SelectField("Patient", coerce=int)
    policy_number = StringField("Policy number", validators=[DataRequired(), Length(min=4, max=40)])
    company_name = StringField("Insurance company", validators=[DataRequired(), Length(max=120)])
    coverage_percent = DecimalField("Coverage %", places=2, validators=[InputRequired(), NumberRange(min=0, max=100)])
    max_coverage = DecimalField("Maximum coverage (₹)", places=2, validators=[InputRequired(), NumberRange(min=0)])
    status = SelectField("Status", choices=[("active", "Active"), ("expired", "Expired"), ("suspended", "Suspended")])
    valid_until = DateField("Valid until", validators=[Optional()])
    submit = SubmitField("Save policy")


class AppointmentStatusForm(FlaskForm):
    submit = SubmitField("Save")
