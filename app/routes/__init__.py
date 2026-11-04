from flask import current_app, flash, request


def paginate(query):
    page = request.args.get("page", 1, type=int)
    return query.paginate(page=max(page, 1), per_page=current_app.config["PER_PAGE"], error_out=False)


def flash_form_errors(form):
    """Show field errors as a flash too (they are also shown beside each field)."""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{getattr(form, field).label.text if hasattr(form, field) else field}: {error}", "danger")


def register_blueprints(app):
    from app.routes.admin import admin_bp
    from app.routes.appointments import appointments_bp
    from app.routes.auth import auth_bp
    from app.routes.doctor import doctor_bp
    from app.routes.main import main_bp
    from app.routes.nurse import nurse_bp
    from app.routes.patient import patient_bp
    from app.routes.payments import payments_bp
    from app.routes.reports import reports_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp, url_prefix="/patient")
    app.register_blueprint(appointments_bp, url_prefix="/appointments")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(reports_bp, url_prefix="/documents")
    app.register_blueprint(doctor_bp, url_prefix="/doctor")
    app.register_blueprint(nurse_bp, url_prefix="/nurse")
    app.register_blueprint(admin_bp, url_prefix="/admin")
