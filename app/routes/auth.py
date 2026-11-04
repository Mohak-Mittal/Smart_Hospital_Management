"""Login, logout, registration, password change."""
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import ChangePasswordForm, LoginForm, RegisterForm
from app.models import Patient, User
from app.models.activity import log_activity
from app.utils.decorators import role_home_url
from app.utils.id_generator import finalize_code, temp_code
from app.utils.validators import is_safe_redirect

auth_bp = Blueprint("auth", __name__)

# Simple in-memory login throttle: {(ip, email): [timestamps]}.  Resets when the
# server restarts and is per-process - fine for a demo (documented in README).
_failed_logins = {}


def reset_login_attempts():
    _failed_logins.clear()


def _recent_failures(key):
    window = current_app.config["LOGIN_LOCKOUT_SECONDS"]
    now = time.time()
    attempts = [t for t in _failed_logins.get(key, []) if now - t < window]
    _failed_logins[key] = attempts
    return attempts


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(role_home_url(current_user))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        key = (request.remote_addr, email)
        if len(_recent_failures(key)) >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
            flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
            return render_template("auth/login.html", form=form), 429
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(form.password.data):
            _failed_logins.pop(key, None)
            login_user(user)
            target = request.args.get("next")
            if target and is_safe_redirect(target, request.host_url):
                return redirect(target)
            return redirect(role_home_url(user))
        _failed_logins.setdefault(key, []).append(time.time())
        flash("Invalid email or password.", "danger")    # same message for both cases on purpose
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(role_home_url(current_user))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            form.email.errors.append("An account with this email already exists.")
        else:
            user = User(email=email, name=form.name.data.strip(), role="patient")
            user.set_password(form.password.data)
            patient = Patient(patient_code=temp_code(), user=user, phone=form.phone.data or None,
                              date_of_birth=form.date_of_birth.data, gender=form.gender.data or None)
            db.session.add_all([user, patient])
            finalize_code(patient, "PAT", "patient_code")
            log_activity(f"New patient registered ({patient.patient_code})", user)
            db.session.commit()
            login_user(user)
            flash("Welcome! Your patient account has been created.", "success")
            return redirect(role_home_url(user))
    return render_template("auth/register.html", form=form)


@auth_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current.data):
            form.current.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(form.password.data)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(role_home_url(current_user))
    return render_template("shared/form.html", form=form, title="Change password",
                           back=role_home_url(current_user), submit_label="Change password")
