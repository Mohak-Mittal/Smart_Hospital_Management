"""Human-friendly codes such as PAT-00007.

Trick used: insert the row with a throw-away unique code, flush to receive the
auto-increment id, then overwrite the code with PREFIX-<id>.  That is safe even
with several simultaneous requests (no "max(id)+1" race).
"""
import uuid

from app.extensions import db


def temp_code() -> str:
    return "TMP-" + uuid.uuid4().hex[:12]


def finalize_code(obj, prefix: str, field: str = "code", width: int = 5) -> str:
    """Call after db.session.add(obj).  Returns the final code."""
    db.session.flush()
    code = f"{prefix}-{obj.id:0{width}d}"
    setattr(obj, field, code)
    return code
