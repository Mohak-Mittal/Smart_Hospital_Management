"""Application factory."""
import sqlite3
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from flask import Flask, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from app.extensions import csrf, db, login_manager, migrate


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores foreign keys unless asked."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def inr(value, decimals=2):
    """Format as Indian rupees with lakh/crore grouping, e.g. ₹1,25,000.00"""
    try:
        value = Decimal(str(value))
    except Exception:
        return value
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail, groups = whole[:-3], whole[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if decimals else "")


BADGES = {
    "scheduled": "primary", "completed": "success", "cancelled": "secondary", "pending": "warning",
    "emergency": "danger", "paid": "success", "PAID": "success", "PENDING": "warning",
    "PARTIALLY_PAID": "info", "partially_paid": "info", "refunded": "secondary",
    "partially_refunded": "secondary", "failed": "danger", "success": "success",
    "published": "success", "draft": "secondary", "active": "success", "expired": "secondary",
    "suspended": "warning", "planned": "info", "in_progress": "primary", "waiting": "warning",
    "in_treatment": "primary", "resolved": "success", "critical": "danger",
}
PRIORITY_BADGES = {1: "danger", 2: "warning", 3: "info", 4: "secondary"}


def create_app(config_class=Config, overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    if overrides:
        app.config.update(overrides)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registers all tables)
    from app.routes import register_blueprints
    register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if request.endpoint and request.endpoint != "static":
            response.headers.setdefault("Cache-Control", "no-store")   # keep patient pages out of caches
        return response

    return app


def _register_template_helpers(app):
    app.jinja_env.filters["inr"] = inr
    app.jinja_env.filters["dt"] = lambda v: v.strftime("%d %b %Y, %I:%M %p") if isinstance(v, datetime) else (v or "-")
    app.jinja_env.filters["dfmt"] = lambda v: v.strftime("%d %b %Y") if v else "-"
    app.jinja_env.filters["tfmt"] = lambda v: v.strftime("%I:%M %p") if isinstance(v, (datetime, time)) else "-"
    app.jinja_env.filters["pretty"] = lambda v: str(v or "").replace("_", " ").title()

    @app.context_processor
    def inject():
        from app.utils.timeutil import hospital_now

        def page_url(page):
            args = {**(request.view_args or {}), **request.args.to_dict(), "page": page}
            return url_for(request.endpoint, **args)

        def badge(status):
            return BADGES.get(status, "secondary")

        return {"HOSPITAL_NAME": app.config["HOSPITAL_NAME"], "page_url": page_url, "badge": badge,
                "priority_badge": lambda p: PRIORITY_BADGES.get(p, "secondary"),
                "hospital_now": hospital_now}


def _register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_template("errors/403.html",
                               message="Your form session expired or was invalid. Go back, refresh the page and try again."), 403

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return render_template("errors/500.html"), 500
