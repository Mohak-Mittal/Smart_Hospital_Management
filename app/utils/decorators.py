"""Authorization decorators.  These run on the SERVER for every request."""
from functools import wraps

from flask import abort
from flask_login import current_user

from app.extensions import login_manager


def role_required(*roles):
    """Allow only logged-in users whose role is in `roles`; otherwise 401/403."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def role_home_url(user) -> str:
    """Where each role lands after login."""
    from flask import url_for
    endpoint = {"patient": "patient.dashboard", "doctor": "doctor.dashboard",
                "nurse": "nurse.dashboard", "admin": "admin.dashboard"}.get(user.role, "main.index")
    return url_for(endpoint)
