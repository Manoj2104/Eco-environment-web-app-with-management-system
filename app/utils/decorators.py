from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def roles_required(*roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("You must be logged in.", "danger")
                return redirect(url_for("auth.login"))

            if current_user.role not in roles:
                flash("Access denied: Insufficient role.", "danger")
                return redirect(url_for("dashboard.index"))

            return fn(*args, **kwargs)
        return decorated_view
    return wrapper
