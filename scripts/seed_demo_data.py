"""Fill the database with fictional demo data.   Usage:  python scripts/seed_demo_data.py [--reset]

All accounts share ONE demo password (config DEMO_PASSWORD).  Local demo use only!
"""
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (Appointment, Doctor, EmergencyCase, InsurancePolicy, MedicalReport, Medicine,  # noqa: E402
                        Nurse, Patient, Room, RoomType, Specialization, User)
from app.services import (appointment_service, billing_service, emergency_service, inventory_service,
                          payment_service, room_service, treatment_service)
from app.utils.id_generator import finalize_code, temp_code  # noqa: E402
from app.utils.timeutil import hospital_now  # noqa: E402


def make_user(email, name, role, password):
    user = User(email=email, name=name, role=role)
    user.set_password(password)
    db.session.add(user)
    return user


def seed(app=None, reset=False):
    app = app or create_app()
    with app.app_context():
        if reset:
            db.drop_all()
        db.create_all()
        if User.query.first():
            print("Database already has data. Use --reset to start over.")
            return
        pw = app.config["DEMO_PASSWORD"]
        now = hospital_now()

        # ---- reference data (fees are DATA, editable by admin) ----
        specs = {}
        for name, key, fee, desc in [("General Physician", "general", 500, "Everyday health problems"),
                                     ("Cardiologist", "cardiologist", 1500, "Heart specialist"),
                                     ("Neurologist", "neurologist", 1800, "Brain & nerves specialist"),
                                     ("Surgeon", "surgeon", 2500, "Surgical consultation")]:
            specs[key] = Specialization(name=name, policy_key=key, base_fee=Decimal(fee), description=desc)
            db.session.add(specs[key])
        types = {}
        for name, rate in [("General Ward", 1000), ("Private Room", 3000), ("ICU", 7000), ("Emergency Room", 5000)]:
            types[name] = RoomType(name=name, daily_rate=Decimal(rate))
            db.session.add(types[name])
        db.session.flush()

        # ---- staff ----
        make_user("admin@hospital.demo", "Anita Admin", "admin", pw)
        docs = []
        for email, name, key, dept, qual, yrs, bio in [
            ("doctor@hospital.demo", "Rohan Mehta", "general", "General Medicine", "MBBS, MD", 12, "Family doctor focused on preventive care."),
            ("cardio@hospital.demo", "Meera Kapoor", "cardiologist", "Cardiology", "MBBS, DM Cardiology", 15, "Heart rhythm and prevention."),
            ("neuro@hospital.demo", "Arjun Rao", "neurologist", "Neurology", "MBBS, DM Neurology", 10, "Headache and nerve disorders."),
            ("surgeon@hospital.demo", "Sunita Verma", "surgeon", "Surgery", "MBBS, MS Surgery", 18, "General and laparoscopic surgery.")]:
            u = make_user(email, name, "doctor", pw)
            d = Doctor(doctor_code=temp_code(), user=u, specialization=specs[key], department=dept,
                       qualification=qual, experience_years=yrs, bio=bio, phone="9876500000",
                       working_days="0,1,2,3,4,5" if key == "general" else "0,1,2,3,4",
                       start_time=time(9, 0), end_time=time(17, 0), slot_minutes=30)
            db.session.add(d)
            db.session.flush()
            finalize_code(d, "DOC", "doctor_code")
            docs.append(d)
        nu = make_user("nurse@hospital.demo", "Nisha Nair", "nurse", pw)
        nurse = Nurse(nurse_code=temp_code(), user=nu, ward="General Ward", shift="Day", phone="9876511111")
        db.session.add(nurse)
        db.session.flush()
        finalize_code(nurse, "NUR", "nurse_code")

        # ---- patients ----
        pats = []
        for email, name, dob, blood, hist in [
            ("patient@hospital.demo", "Priya Sharma", date(1990, 5, 14), "B+", "Demo history: seasonal allergies."),
            ("patient2@hospital.demo", "Vikram Singh", date(1982, 11, 2), "O+", "Demo history: mild hypertension."),
            ("patient3@hospital.demo", "Kavya Iyer", date(1998, 3, 27), "A+", "Demo history: none recorded."),
            ("patient4@hospital.demo", "Imran Khan", date(1975, 8, 9), "AB-", "Demo history: knee pain.")]:
            u = make_user(email, name, "patient", pw)
            p = Patient(patient_code=temp_code(), user=u, date_of_birth=dob, blood_group=blood, phone="98765" + str(10000 + len(pats)),
                        gender="Female" if name.split()[0] in ("Priya", "Kavya") else "Male", address="12 Demo Street, Sample City",
                        emergency_contact="Family member 9000000000")
            p.medical_history = hist
            db.session.add(p)
            db.session.flush()
            finalize_code(p, "PAT", "patient_code")
            pats.append(p)
        db.session.commit()
        priya, vikram, kavya, imran = pats
        nurse.assigned_patients.append(vikram)

        # ---- rooms, medicines, insurance ----
        rooms = []
        for number, t in [("G-101", "General Ward"), ("G-102", "General Ward"), ("P-201", "Private Room"),
                          ("P-202", "Private Room"), ("ICU-1", "ICU"), ("ER-1", "Emergency Room")]:
            r = Room(room_number=number, room_type_id=types[t].id, floor=number.split("-")[0])
            db.session.add(r)
            rooms.append(r)
        meds = []
        for name, cat, price, qty, low in [("Paracetamol 500mg", "Analgesic", 2, 500, 50), ("Amoxicillin 250mg", "Antibiotic", 8, 200, 40),
                                           ("Atorvastatin 10mg", "Cardiac", 12, 120, 30), ("Insulin Pen", "Diabetes", 450, 8, 10),
                                           ("ORS Sachet", "Rehydration", 15, 3, 20), ("Cetirizine 10mg", "Antihistamine", 3, 300, 40)]:
            m = Medicine(medicine_code=temp_code(), name=name, category=cat, price=Decimal(price), quantity=0, reorder_level=low)
            db.session.add(m)
            db.session.flush()
            finalize_code(m, "MED", "medicine_code")
            inventory_service.add_stock(m, qty, "Opening stock", None, commit=False) if qty else None
            meds.append(m)
        db.session.add(InsurancePolicy(patient_id=vikram.id, policy_number="HLTH-2026-004821", company_name="SafeLife Insurance (demo)",
                                       coverage_percent=Decimal("80"), max_coverage=Decimal("30000"), status="active",
                                       valid_until=now.date() + timedelta(days=365)))
        db.session.commit()
        admin = User.query.filter_by(role="admin").first()

        # ---- appointments (paid + one pending) ----
        def next_slot(doc, days, hour=10, minute=0):
            day = now.date() + timedelta(days=days)
            while day.weekday() not in doc.working_day_numbers:
                day += timedelta(days=1)
            return datetime.combine(day, time(hour, minute))

        general, cardio = docs[0], docs[1]
        a1 = appointment_service.book_appointment(priya, general, next_slot(general, 2, 10), "Seasonal allergy check")
        payment_service.pay_appointment(a1, "upi", {"upi_id": "priya@demobank"}, priya.user)
        a2 = appointment_service.book_appointment(kavya, cardio, next_slot(cardio, 3, 11), "Palpitations - demo")
        payment_service.pay_appointment(a2, "card", {"card_name": "Kavya Iyer", "card_number": "4242424242424242",
                                                     "card_expiry": f"12/{(now.year + 3) % 100:02d}", "card_cvv": "123"}, kavya.user)
        appointment_service.book_appointment(imran, general, next_slot(general, 4, 15), "Knee pain")   # left pending (unpaid)

        # Vikram: completed visit (booked in the past by inserting directly) + treatment + published/unpublished reports
        past = datetime.combine(now.date() - timedelta(days=1), time(10, 0))
        done = Appointment(code=temp_code(), patient_id=vikram.id, doctor_id=general.id, start_time=past,
                           end_time=past + timedelta(minutes=30), status="scheduled", payment_status="paid",
                           fee=general.calculate_consultation_fee(), reason="Blood pressure review")
        db.session.add(done)
        finalize_code(done, "APT")
        db.session.commit()
        from app.models import PaymentTransaction
        db.session.add(PaymentTransaction(txn_ref=temp_code(), patient_id=vikram.id, appointment_id=done.id, kind="consultation",
                                          method="upi", amount=done.fee, status="success", detail="UPI vi***@demobank"))
        db.session.flush()
        for txn in PaymentTransaction.query.filter(PaymentTransaction.txn_ref.like("TMP-%")):
            finalize_code(txn, "TXN", "txn_ref", width=6)
        db.session.commit()
        appointment_service.record_consultation(done, "Mild hypertension (demo)", "Advised lifestyle changes; demo notes only.")
        appointment_service.complete_appointment(done)

        plan = treatment_service.create_plan(general, vikram, "medicine", "Mild hypertension (demo)", "Daily medication and weekly review.",
                                             {"medicine_charges": "1800", "consultation_charges": "0"})
        treatment_service.set_status(plan, "in_progress", general.user)
        treatment_service.add_progress(plan, general.user, "progress", "Blood pressure readings improving (demo).")
        treatment_service.add_progress(plan, general.user, "medication", "Atorvastatin 10mg once daily (demo entry).")
        treatment_service.add_progress(plan, nu, "nursing", "Vitals checked, patient comfortable (demo).")
        room_service.assign_room(rooms[0], vikram, admin)       # G-101 occupied
        rep1 = MedicalReport(report_code=temp_code(), patient_id=vikram.id, doctor_id=general.id, appointment_id=done.id,
                             title="Consultation summary (demo)", content="Patient reviewed for blood pressure.\nPlan: medication and follow-up.\nThis is fictional demo content.",
                             status="published", published_at=now)
        rep2 = MedicalReport(report_code=temp_code(), patient_id=vikram.id, doctor_id=general.id,
                             title="Follow-up plan (draft)", content="Draft follow-up plan - not yet published.", status="draft")
        for r in (rep1, rep2):
            db.session.add(r)
        db.session.flush()
        finalize_code(rep1, "REP", "report_code")
        finalize_code(rep2, "REP", "report_code")
        db.session.commit()
        bill = billing_service.create_bill(vikram, admin, True, [(meds[0], 10)], "Demo bill")
        payment_service.pay_bill(bill, "cash", min(bill.balance_due, Decimal("500")), {}, admin)   # partial payment

        # ---- emergency queue ----
        emergency_service.add_case("Ramesh Gupta", "Chest pain, sweating", 2, age=58, user=admin)
        emergency_service.add_case("Child walk-in", "Fever and rash", 3, age=6, user=admin)
        emergency_service.add_case(None, "Road accident - heavy bleeding", 1, patient=imran, user=admin)
        emergency_service.add_case("Sana Ali", "Minor cut on hand", 4, age=24, user=admin)
        print("Demo data created.  Password for every demo account:", pw)
        print("Admin: admin@hospital.demo | Doctor: doctor@hospital.demo | Nurse: nurse@hospital.demo | Patient: patient@hospital.demo")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
