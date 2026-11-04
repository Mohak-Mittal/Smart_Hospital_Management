# Class diagram

```mermaid
classDiagram
    direction LR
    class User {
        +id
        +email
        +password_hash
        +role
        +active
        +set_password()
        +check_password()
    }
    class HospitalUser {
        <<abstract>>
        +phone
        +full_name
        +display_details()
        +__str__()
    }
    class Patient {
        +patient_code
        -__medical_history
        -__wallet_balance
        +medical_history
        +credit_wallet()
        +debit_wallet()
        +active_policy
        +display_details()
        +__eq__()
    }
    class Doctor {
        +doctor_code
        +working_days
        +fee_override
        +calculate_consultation_fee()
        +is_bookable
        +display_details()
    }
    class Nurse {
        +nurse_code
        +ward
        +assigned_patients
    }
    User "1" --> "0..1" Patient
    User "1" --> "0..1" Doctor
    User "1" --> "0..1" Nurse
    HospitalUser <|-- Patient
    HospitalUser <|-- Doctor
    HospitalUser <|-- Nurse

    class SpecializationPolicy {
        <<abstract>>
        +calculate_consultation_fee()*
        +display_details()
    }
    SpecializationPolicy <|-- GeneralPhysicianPolicy
    SpecializationPolicy <|-- CardiologistPolicy
    SpecializationPolicy <|-- NeurologistPolicy
    SpecializationPolicy <|-- SurgeonPolicy
    class Specialization { +name +policy_key +base_fee }
    Doctor --> Specialization
    Specialization ..> SpecializationPolicy : policy_key lookup

    class Treatment {
        <<abstract>>
        +perform_treatment()*
        +calculate_cost()*
    }
    Treatment <|-- MedicineTreatment
    Treatment <|-- SurgeryTreatment
    Treatment <|-- PhysiotherapyTreatment
    Treatment <|-- EmergencyTreatment
    class TreatmentPlan { +treatment_type +status +params +as_treatment() +cost }
    TreatmentPlan ..> Treatment : builds via registry
    TreatmentPlan "1" --> "*" TreatmentProgress
    Patient "1" --> "*" TreatmentPlan
    Doctor "1" --> "*" TreatmentPlan

    class Payment {
        <<abstract>>
        +process_payment()*
        +display_details()
    }
    Payment <|-- UPIPayment
    Payment <|-- CardPayment
    Payment <|-- CashPayment
    Payment <|-- InsurancePayment
    class PaymentTransaction { +txn_ref +method +amount +status +counts_toward_balance }
    Payment ..> PaymentTransaction : result recorded as

    class Appointment { +status +payment_status +fee +start_time }
    Patient "1" --> "*" Appointment
    Doctor "1" --> "*" Appointment

    class Bill { +subtotal +insurance_coverage +final_amount +balance_due +status }
    class BillItem
    class InsurancePolicy { +coverage_percent +max_coverage +calculate_coverage() }
    class ChargeSummary { +total +__add__() }
    Bill "1" --> "*" BillItem
    Bill --> InsurancePolicy
    Patient "1" --> "*" Bill
    Patient "1" --> "*" InsurancePolicy
    Bill "1" --> "*" PaymentTransaction

    class MedicalReport { +status +publish }
    Doctor "1" --> "*" MedicalReport
    Patient "1" --> "*" MedicalReport

    class Medicine { +quantity +price }
    class StockMovement
    Medicine "1" --> "*" StockMovement

    class RoomType { +daily_rate }
    class Room
    class RoomAssignment { +assigned_at +released_at }
    Room --> RoomType
    Room "1" --> "*" RoomAssignment
    Patient "1" --> "*" RoomAssignment

    class EmergencyCase { +priority +arrived_at +__lt__() }
    class EmergencyQueue { +push() +pop() +ordered() +__len__() }
    EmergencyQueue o-- EmergencyCase
    class Discharge
    Patient "1" --> "*" Discharge
```

`*` after a method name marks it **abstract**. Service classes/modules (`appointment_service`, `payment_service`,
`billing_service`, `inventory_service`, `room_service`, `emergency_service`, `treatment_service`,
`discharge_service`) hold the business rules that coordinate these classes.
