"""Import every model so SQLAlchemy knows all tables."""
from app.models.activity import ActivityLog, log_activity  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.bill import Bill, BillItem, ChargeSummary  # noqa: F401
from app.models.doctor import Doctor, Specialization  # noqa: F401
from app.models.emergency import Discharge, EmergencyCase  # noqa: F401
from app.models.insurance import InsurancePolicy  # noqa: F401
from app.models.medical_report import MedicalReport  # noqa: F401
from app.models.medicine import Medicine, StockMovement  # noqa: F401
from app.models.nurse import Nurse, nurse_patients  # noqa: F401
from app.models.patient import Patient  # noqa: F401
from app.models.payment import PaymentTransaction  # noqa: F401
from app.models.room import Room, RoomAssignment, RoomType  # noqa: F401
from app.models.treatment import TreatmentPlan, TreatmentProgress  # noqa: F401
from app.models.user import HospitalUser, User  # noqa: F401
