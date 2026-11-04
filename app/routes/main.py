from flask import Blueprint, redirect, render_template
from flask_login import current_user

from app.models import Doctor, Specialization
from app.utils.decorators import role_home_url

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(role_home_url(current_user))
    specs = Specialization.query.order_by(Specialization.base_fee).all()
    return render_template("landing.html", specs=specs, doctor_count=Doctor.query.count())
