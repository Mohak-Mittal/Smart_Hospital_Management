from app.extensions import db
from app.utils.timeutil import hospital_now


class ActivityLog(db.Model):
    """Short, NON-medical audit lines shown as 'Recent activity' (no clinical data here)."""
    __tablename__ = "activity_logs"
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=hospital_now, index=True)


def log_activity(message: str, user=None):
    db.session.add(ActivityLog(message=message[:255], actor_user_id=getattr(user, "id", None)))
