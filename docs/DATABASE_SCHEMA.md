# Database schema

SQLite by default (`instance/hospital.db`). Money columns use a custom `Money` type: an **integer number of
paise** in the database, `Decimal` in Python (exact, no float errors). The same type stores percentages (80.00).
All timestamps are hospital-local naive datetimes. Foreign keys are enforced (`PRAGMA foreign_keys=ON`).

| Table | Purpose | Key columns / constraints |
|---|---|---|
| `users` | Login accounts | `email` UNIQUE, `password_hash`, `role` CHECK in (patient, doctor, nurse, admin), `active` |
| `patients` | Patient profile | `patient_code` UNIQUE, `user_id` UNIQUE FK, DOB, blood group, `medical_history`, `wallet_balance` |
| `specializations` | Specialization + **configurable base fee** | `name` UNIQUE, `policy_key`, `base_fee` |
| `doctors` | Doctor profile + schedule | `doctor_code` UNIQUE, `user_id` UNIQUE FK, `specialization_id` FK, `fee_override`, `working_days`, `start_time`, `end_time`, `slot_minutes` CHECK 10–120, `accepting_appointments` |
| `nurses` | Nurse profile | `nurse_code` UNIQUE, `user_id` UNIQUE FK, ward, shift |
| `nurse_patients` | Nurse ↔ patient assignment | composite PK (nurse_id, patient_id) |
| `appointments` | Bookings | `code` UNIQUE, patient/doctor FKs, `start_time`, `status` CHECK (pending, scheduled, completed, cancelled, emergency), `payment_status` CHECK, `fee`, `refund_amount`, consultation fields; **partial UNIQUE index** `(doctor_id, start_time) WHERE status IN ('pending','scheduled','completed')` = no double booking; `bill_id` FK |
| `treatment_plans` | Treatments | `code` UNIQUE, patient/doctor FKs, `treatment_type`, `status` CHECK, `params` JSON (charges), `doctor_approved_at`, `discharged_at`, `bill_id` FK |
| `treatment_progress` | Timeline notes | `treatment_id` FK, `kind` (progress, medication, nursing, status), `note` |
| `medical_reports` | Reports | `report_code` UNIQUE, patient/doctor FKs, `status` CHECK (draft, published), `published_at` |
| `medicines` | Inventory | `medicine_code` UNIQUE, `price` ≥ 0, `quantity` **CHECK ≥ 0**, `reorder_level` |
| `stock_movements` | Stock audit trail | `medicine_id` FK, `change`, `balance_after`, `reason`, `user_id` |
| `room_types` | Room types + **configurable daily rate** | `name` UNIQUE, `daily_rate` |
| `rooms` | Rooms | `room_number` UNIQUE, `room_type_id` FK, `active` |
| `room_assignments` | Stays | room/patient FKs, `assigned_at`, `released_at`; **partial UNIQUE indexes** on `room_id` and on `patient_id` `WHERE released_at IS NULL` = one active stay each; `bill_id` FK |
| `insurance_policies` | Policies | `policy_number` UNIQUE, `coverage_percent`, `max_coverage`, `status` CHECK (active, expired, suspended), `valid_until` |
| `bills` | Invoices | `invoice_number` UNIQUE, six charge columns, `insurance_coverage`, `amount_paid`, `status` CHECK (PENDING, PARTIALLY_PAID, PAID), `insurer_settled` |
| `bill_items` | Invoice lines | `bill_id` FK, category, description, quantity, unit_price, amount |
| `payment_transactions` | Every payment attempt (success or failed) | `txn_ref` UNIQUE, `method` CHECK (upi, card, cash, insurance), `status` CHECK, `detail` (e.g. `Visa ****4242` only), `counts_toward_balance` (false for insurer settlement), appointment/bill FKs |
| `emergency_cases` | Emergency queue | `case_code` UNIQUE, nullable `patient_id` (walk-ins), `priority` CHECK 1–4, `status` CHECK, `arrived_at` |
| `discharges` | Discharge records | patient FK, `discharged_at`, `room_released` |
| `activity_logs` | Recent-activity feed (non-medical text only) | `message`, `actor_user_id`, `created_at` |

## Key relationships
`users 1─0..1 patients/doctors/nurses` · `patients 1─* appointments/treatment_plans/bills/payment_transactions/insurance_policies/room_assignments/medical_reports` ·
`doctors 1─* appointments/treatment_plans/medical_reports` · `bills 1─* bill_items/payment_transactions` · `rooms 1─* room_assignments`.

## Concurrency note
Two simultaneous booking attempts: the second `INSERT` violates `uq_doctor_active_slot` and is reported as
"slot just booked". SQLite takes a database-wide write lock, so this is safe but not highly concurrent.
