# User guide

Sign in at `/login` (demo accounts and the shared password are in the README). A visible banner reminds
you everywhere: **demo data, simulated payments, no real money.**

## Patient
1. **Register** (landing page → *Register as a patient*) or use `patient@hospital.demo`.
2. **Find a doctor**: search by name/specialization/department and max fee. Open a profile to see the fee, working days and **free slots**.
3. **Book**: pick a date chip and a time, add an optional reason, *Reserve slot & continue to payment*. The slot is held for **15 minutes**.
4. **Pay (demo)**: choose UPI, card or cash. Only after the payment succeeds is the appointment **Scheduled** and a receipt shown. A failed payment leaves it *Pending* so you can retry.
5. **Appointments** tab: Upcoming / Pending payment / Completed / Cancelled. *Cancel* policy: not within 2 hours of the start; refund 100% if ≥ 24 h ahead, otherwise 50% (simulated).
6. **Treatment status**: plan, status, discharge approval and timeline notes (doctor + nursing), plus room history.
7. **Reports**: only reports your doctor has **published**; view or download PDF.
8. **Invoices & payments**: invoices (view / PDF / pay balance), full payment history, outstanding balance and your insurance summary (e.g. ₹50,000 bill with 80% / ₹30,000 cap → insurer ₹30,000, you ₹20,000).
9. **My profile**: edit contact details and self-reported history.

## Doctor
* **Dashboard**: today's and upcoming appointments, open treatments, draft reports.
* **Open record** (only patients linked to you through a *confirmed* appointment, emergency assignment or treatment — otherwise you get *403*).
* **Consultation**: enter diagnosis + notes → *Save consultation*. Only then can you *Mark appointment completed*.
* **Treatment plan**: choose Medicine / Surgery / Physiotherapy / Emergency; the matching charge fields appear. Costs: medicine = medicine + consultation; surgery = operation + surgeon + hospital; physiotherapy = session × sessions; emergency = emergency + treatment. Move it *Start → Mark completed*, add progress/medication entries, then *Approve discharge*.
  Leave *Consultation charges* at 0 when the appointment fee is already billed from the appointment.
* **Reports**: save a draft, then *Publish* (only the author can publish). Patients see it only after publishing. Download PDFs any time.

## Nurse
*My patients* lists patients the admin assigned to you. Open one to read the treatment timeline and add **nursing notes**. Nurses cannot change treatment status.

## Admin / reception
* **Dashboard**: patients/doctors/nurses, today's & upcoming appointments, emergency queue, rooms occupied/available, pending bills, low-stock medicines, recent activity, charts.
* **Doctors**: add/edit/deactivate, stop/allow bookings, set working days/hours/slot length, per-doctor fee override, and edit the **consultation fee per specialization** (seeded: General ₹500, Cardiologist ₹1,500, Neurologist ₹1,800, Surgeon ₹2,500).
* **Nurses**: add/edit/deactivate, assign patients. **Patients**: search, edit, deactivate.
* **Appointments**: filter, cancel (full refund), or *Receive cash* for a pending booking.
* **Rooms**: assign/release; occupied rooms cannot be assigned again. Rates (General Ward ₹1,000, Private ₹3,000, ICU ₹7,000, Emergency Room ₹5,000 per day) are editable. Charge = rate × days, every started 24 h counts as a day, minimum 1 day.
* **Medicines**: add, edit, *+ Stock* / *− Stock* (cannot go below zero), view history.
* **Emergency queue**: add a case (registered patient or walk-in) with Level 1–4; the queue is sorted automatically (lower level first; ties by arrival). Change priority, assign a doctor (registered patients get an *emergency* appointment so the doctor can open the record), mark resolved.
* **Billing**: *Generate bill* collects the patient's unbilled paid consultations, in-progress/completed treatments, room stays and up to three pharmacy items. Insurance is applied automatically (tick/untick). Record payments (partial payments → *Partially paid*), record the **insurer settlement**, open the printable invoice or PDF.
  Note: a room stay is billed once at the billing moment; billing again later will not re-charge that stay.
* **Insurance**: add/edit policies (number, company, %, max, status, validity).
* **Discharges**: each patient shows the 4 conditions (treatment completed, doctor approval, bill generated, payment completed incl. insurer settlement). *Discharge* is enabled when all are met; *Try discharge* shows exactly what is missing. A successful discharge releases the room.

## Typical end-to-end demo (5 minutes)
1. Patient `patient@hospital.demo` books Dr. Mehta and pays with UPI `me@bank`.
2. Doctor `doctor@hospital.demo` opens Priya, records a consultation, completes the visit, writes + publishes a report.
3. Patient downloads the report PDF.
4. Admin `admin@hospital.demo` generates a bill for Priya, records a payment, and downloads the invoice PDF.
5. Admin opens *Discharges* for Vikram (`patient2@hospital.demo`) and sees which conditions block discharge. Then Dr. Mehta marks his treatment completed and approves discharge, admin generates a new bill if needed, collects the balance, records the insurer settlement, and discharges him — his room is released.
