# Project overview

**Smart Hospital Management & Emergency Response System** is a Flask application that models a small
hospital. It is a *learning/demo* project: data and payments are fictional and no compliance is claimed.

## Architecture

```
Browser ──► Flask routes (app/routes)  ──►  Services (app/services)  ──►  Models (app/models)  ──►  SQLite
              auth, authorization,           business rules,              tables + OOP behaviour
              forms, templates               transactions
```

* **Application factory** (`app/__init__.py: create_app`) — builds the app, registers extensions and blueprints. Tests create a fresh app per test.
* **Routes stay thin.** They check *who you are*, validate the form, call a service, and render a template.
* **Services hold the rules** (e.g. "a slot cannot be double-booked", "stock cannot go negative"). They raise friendly exceptions (`BookingError`, `InventoryError` …) that routes show as flash messages.
* **Models** contain data plus behaviour that belongs to the object (fees, costs, coverage, priority comparison).

## Security model
* Passwords: salted hashes (Werkzeug). Sessions: Flask-Login. Every POST: CSRF token (Flask-WTF).
* **Authorization on the server for every route**: `@role_required(...)` decorators; the whole admin blueprint has a `before_request` guard; ownership checks (`patient_id == my id`, doctor↔patient link) live in `app/services/access.py`.
* Safe redirects after login, output escaping (Jinja autoescape; ReportLab text escaped), strict Content-Security-Policy (no inline scripts), `no-store` caching for pages, security headers.
* Card number / CVV are validated in memory only and never stored or logged.
* Login throttling (in memory), inactive accounts lose their session immediately.

## The four OOP pillars (where to look)

| Pillar | Example in the code |
|---|---|
| **Inheritance** | `HospitalUser` (abstract base, `app/models/user.py`) → `Patient`, `Doctor`, `Nurse`; `Payment` → `UPIPayment`, `CardPayment`, `CashPayment`, `InsurancePayment`; `Treatment` → 4 treatment types; `SpecializationPolicy` → 4 specializations |
| **Encapsulation** | `Patient.__medical_history`, `__wallet_balance` accessed via properties/`credit_wallet`/`debit_wallet`; stock changes only through `inventory_service`. Name mangling is *not* security (see README) |
| **Abstraction** | `abc.ABC` + `@abstractmethod`: `Payment.process_payment()`, `Treatment.perform_treatment()` / `calculate_cost()`, `SpecializationPolicy.calculate_consultation_fee()` |
| **Polymorphism** | Overridden `display_details()`, `calculate_consultation_fee()`, `calculate_cost()`, `process_payment()`; objects are picked from **registries** (`PAYMENT_REGISTRY`, `TREATMENT_REGISTRY`, `POLICY_REGISTRY`) instead of `if/elif` chains |

Magic methods: `__str__` (several classes), `__eq__`/`__hash__` (`Patient`, by patient ID), `__lt__` (`EmergencyCase`, priority then arrival), `__add__` (`ChargeSummary`), `__len__` (`EmergencyQueue`). `Patient` deliberately exposes `record_count` instead of `__len__`, because a `__len__` of 0 would make an empty patient record "falsy" and cause subtle `if patient:` bugs.

## Key business rules
* **Booking**: slot must be on the doctor's schedule, in the future, within 30 days, doctor accepting + account active. The slot is *held* (status `pending`) for 15 minutes; the booking becomes `scheduled` **only after the simulated payment succeeds**.
* **Cancellation**: not within 2 h of start; refund 100% if ≥ 24 h ahead, else 50% (simulated). Admin cancellations refund 100%.
* **Insurance**: insurer share = `min(bill × coverage%, policy maximum, bill)`; patient share = bill − insurer share. Insurer share is tracked as `insurance_coverage` on the bill (not as a patient payment), and the insurer's later settlement is a separate transaction that does not touch the patient's balance.
* **Rooms**: one active stay per room and per patient (service check + partial unique indexes). Charge = daily rate × days; every *started* 24 h = 1 day, minimum 1 day.
* **Emergency queue**: Level 1 (Critical) … 4 (Minor); lower number first; equal levels keep arrival order (`heapq` + `__lt__` + sequence tie-break).
* **Discharge** needs all four: treatment completed, doctor approval, bill generated, patient balance zero (and insurer share settled when insurance applies). Unmet items are listed. Discharge releases the room.

## Technology
Flask 3 · Flask-SQLAlchemy/SQLAlchemy 2 · Flask-Login · Flask-WTF/WTForms · Flask-Migrate · SQLite · ReportLab · Bootstrap 5 · Chart.js · pytest.
