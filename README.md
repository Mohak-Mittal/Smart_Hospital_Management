# Smart Hospital Management & Emergency Response System

A complete, runnable **demo** hospital web app built with Python, Flask and SQLite. It has three
role-based portals (patient, doctor, admin/reception) plus a basic nurse portal, all sharing one database.

> **DEMO ONLY.** All people, medicines, diagnoses and reports are fictional. **All payments are
> simulated — no real money is charged and no card data is stored.** This is a learning project, not a
> certified clinical or production hospital system, and it makes no compliance claims (HIPAA, GDPR, etc.).

## Features

| Portal | What you can do |
|---|---|
| **Patient** | Register/login, edit profile, search doctors (name / specialization / department / max fee), see free slots, book, pay the consultation fee (simulated), see pending/upcoming/completed/cancelled appointments, cancel (documented policy), follow the treatment timeline, read published reports, download invoice & report PDFs, view payment history, outstanding balance and insurance cover |
| **Doctor** | Dashboard (today / upcoming), appointment list with payment status, open only *your* patients, record consultation + diagnosis, create treatment plans (4 types), add progress/medication notes, approve discharge, write and **publish** reports, complete appointments (only after a consultation is recorded) |
| **Nurse** | See assigned patients, treatment status and timeline, add nursing notes |
| **Admin / reception** | KPI dashboard + charts, manage doctors/nurses/patients (create, edit, deactivate), consultation fees, working hours, appointments, rooms (assign/release, daily rates), medicine inventory (+/- stock with history), emergency priority queue, bills, insurance policies, payments, insurer settlement, discharge checklist |

Also: Indian-rupee formatting, responsive UI (desktop/tablet/mobile), pagination, search/filters,
confirmation dialogs, validation messages beside fields, 403/404/500 pages, printable HTML invoice fallback.

## Supported Python version

* **Developed and tested on Python 3.12** (all 93 automated tests pass there).
* Should work on 3.10 – 3.13 (all dependencies support them).
* **Python 3.14 was not available in the build environment, so it is untested.** The brief asks for 3.14 where all dependencies support it; I could not verify that, so the pinned versions in `requirements.txt` are the ones that were actually tested. If you use 3.14 and a package fails to install, use Python 3.12 or 3.13 instead.

## Windows setup (step by step)

1. Install Python from <https://www.python.org/downloads/> (tick **"Add python.exe to PATH"** during install).
2. Unzip `Smart_Hospital_Management.zip` and open **PowerShell** inside the `Smart_Hospital_Management` folder
   (in File Explorer: open the folder → click the address bar → type `powershell` → Enter).
3. Create and activate a virtual environment:
   ```powershell
   py -3 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   *If PowerShell says scripts are disabled:* run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again.
   (Command Prompt users: `.venv\Scripts\activate.bat`.)
4. Install the requirements:
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
5. Configure settings (optional but recommended):
   ```powershell
   copy .env.example .env
   ```
   Open `.env` and change `SECRET_KEY` to any long random text. Defaults work for local demos.
6. Create the database tables:
   ```powershell
   python scripts\init_db.py
   ```
7. Load the demo data:
   ```powershell
   python scripts\seed_demo_data.py
   ```
8. Start the server:
   ```powershell
   python run.py
   ```
9. Open <http://127.0.0.1:5000> in your browser. Stop the server with `Ctrl+C`.

(macOS/Linux: same steps with `python3 -m venv .venv`, `source .venv/bin/activate` and forward slashes.)

## Demo credentials (local demonstration only!)

Every seeded account uses the **same password: `Demo@12345`**.

| Role | Email | Notes |
|---|---|---|
| Admin | `admin@hospital.demo` | full hospital access |
| Doctor (General Physician) | `doctor@hospital.demo` | Dr. Rohan Mehta — has the demo patient data |
| Doctor (Cardiologist) | `cardio@hospital.demo` | |
| Doctor (Neurologist) | `neuro@hospital.demo` | |
| Doctor (Surgeon) | `surgeon@hospital.demo` | |
| Nurse | `nurse@hospital.demo` | assigned to patient Vikram Singh |
| Patient | `patient@hospital.demo` | Priya Sharma — has one confirmed booking |
| Patient (insured, admitted) | `patient2@hospital.demo` | Vikram Singh — 80% / ₹30,000 policy, room G-101, treatment, published + draft report, bill |
| Patient | `patient3@hospital.demo` | Kavya Iyer — booked a cardiologist |
| Patient | `patient4@hospital.demo` | Imran Khan — has an unpaid (pending) booking and an emergency case |

These credentials are public in this README. Never use them on a server reachable by others. You can
change your password after signing in (sidebar → *Change password*).

### Handy demo values for the payment page
* UPI: any id like `name@bank` succeeds; ids ending in `@fail` are declined.
* Card: `4242 4242 4242 4242` (any future expiry such as `12/40`, any 3-digit CVV) succeeds;
  `4000 0000 0000 0002` is declined. Card number and CVV are checked in memory and **never stored**.
* Cash: always succeeds and issues a demo receipt.

## Running the tests

```powershell
python -m pytest
```
Every test uses its own temporary database, so your demo data is never touched. Expected result: **93 passed**.

An extra end-to-end check (real CSRF protection, all four roles, throw-away database):
```powershell
python scripts\smoke_test.py
```

## Resetting the demo database

```powershell
python scripts\seed_demo_data.py --reset
```
(drops every table and re-creates the demo data). To start completely empty: stop the server, delete
`instance\hospital.db`, then run `python scripts\init_db.py` again.

## Project layout (short)

```
run.py, config.py            entry point and settings
app/models/                  database tables + OOP classes (inheritance, abstraction, polymorphism…)
app/services/                business rules (booking, payments, billing, inventory, rooms, emergency, discharge)
app/routes/                  thin web routes grouped by portal
app/templates, app/static    pages, CSS/JS, bundled Bootstrap + Chart.js (works offline)
scripts/                     init_db.py, seed_demo_data.py, smoke_test.py
tests/                       pytest suite
docs/                        overview, class diagram, DB schema, user guide
```

## Important design notes & limitations (please read)

* **Payments are simulated.** No gateway, no network calls, no real card handling. Do not add real card processing to this code.
* **Not production-ready.** No audit-grade logging, no encryption at rest, no email/SMS, no HTTPS in the dev server, no backups. Use a real WSGI server, HTTPS, PostgreSQL and a proper secret key if you ever adapt it.
* **SQLite concurrency.** Double booking is prevented by a service check *and* a partial unique database index, so even simultaneous clicks cannot create two active bookings for one doctor/time. SQLite serialises writes; it is fine for a demo but a multi-user deployment should use PostgreSQL.
* **Login rate limiting** is a simple in-memory counter (5 failures → 5-minute lock per IP+email). It resets when the server restarts and is per-process.
* **Time zone.** All times are *hospital local time* stored as naive datetimes. The zone comes from `HOSPITAL_TIMEZONE` in `.env` (default `Asia/Kolkata`).
* **Money** is stored as exact integer paise and handled as `Decimal` (never float). All amounts are INR.
* **Migrations.** Tables are created with `create_all` (scripts/init_db.py). Flask-Migrate is installed and wired in; to adopt migrations later run `flask --app run db init`, `flask --app run db migrate`, `flask --app run db upgrade`.
* **Encapsulation** uses Python name mangling (`__medical_history`). That only discourages accidental access — real access control is login + role checks on the server (see `app/utils/decorators.py`, `app/services/access.py`).
* **Billing simplification.** A bill collects everything *not yet billed* (paid consultations, in-progress/completed treatments, room stays up to the billing moment, pharmacy items you add). A room stay is billed once; if a patient stays on after a bill is generated, generate a new bill/handle manually (documented in `docs/USER_GUIDE.md`).
* Clinical text is demo data; the software does not validate diagnoses and gives no medical advice.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` / `py` not recognised | Re-install Python and tick *Add to PATH*, or use the full path. |
| PowerShell blocks `Activate.ps1` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. |
| `ModuleNotFoundError` (flask, reportlab…) | The virtual environment is not active or requirements are not installed: activate `.venv` and run `python -m pip install -r requirements.txt`. |
| Pillow/reportlab build errors on a very new Python | Use Python 3.12 or 3.13. |
| `Address already in use` / port 5000 busy | Close the other program, or edit the port in `run.py`. |
| `no such table` | Run `python scripts\init_db.py` (and the seed script). |
| `database is locked` | Close other programs using `instance\hospital.db` (e.g. a DB viewer) and retry. |
| Login says too many attempts | Wait 5 minutes or restart the server. |
| "Your form session expired" | Refresh the page and submit again (CSRF protection). |
| Times look wrong | Set `HOSPITAL_TIMEZONE` in `.env` (e.g. `Asia/Kolkata`); `tzdata` is installed for Windows. |
| Demo data missing / messy | `python scripts\seed_demo_data.py --reset` |
| ₹ symbol missing in PDFs | The bundled DejaVu font is in `app/static/fonts`; make sure that folder was not deleted. |

## Third-party assets

Bootstrap 5.3.3 (MIT) and Chart.js 4.4.4 (MIT) are bundled in `app/static/vendor`; DejaVu Sans fonts
(free licence, see `app/static/fonts/DEJAVU_LICENSE.txt`) are bundled for PDF rendering.
