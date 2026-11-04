"""Authentication user + the shared HospitalUser base class (INHERITANCE)."""
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.utils.timeutil import hospital_now

ROLES = ("patient", "doctor", "nurse", "admin")


class User(UserMixin, db.Model):
    """Login account.  Role-specific data lives in Patient/Doctor/Nurse profiles."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=hospital_now)

    __table_args__ = (
        db.CheckConstraint("role IN ('patient','doctor','nurse','admin')", name="ck_user_role"),
    )

    # Flask-Login asks this; a deactivated account cannot log in.
    @property
    def is_active(self):
        return bool(self.active)

    def set_password(self, raw: str):
        """Only a salted hash is stored (never the plain password)."""
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    def has_role(self, *roles) -> bool:
        return self.role in roles

    def __str__(self):
        return f"{self.name} <{self.email}> [{self.role}]"


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    # deactivated users lose their session immediately
    return user if user and user.active else None


class HospitalUser(db.Model):
    """Abstract base for people who have a profile in the hospital.

    `Patient`, `Doctor` and `Nurse` INHERIT the shared columns and behaviour.
    Because __abstract__ = True, no table is created for this class itself.
    """
    __abstract__ = True

    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=hospital_now)

    @property
    def full_name(self) -> str:
        return self.user.name if getattr(self, "user", None) else "(unknown)"

    @property
    def email(self) -> str:
        return self.user.email if getattr(self, "user", None) else ""

    def display_details(self) -> dict:
        """Polymorphic: every subclass overrides this to add its own details."""
        return {"Name": self.full_name, "Email": self.email, "Phone": self.phone or "-"}

    def __str__(self):
        return f"{self.__class__.__name__}: {self.full_name}"
