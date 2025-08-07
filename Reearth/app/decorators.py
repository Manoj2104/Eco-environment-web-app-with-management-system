from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please login first.", "warning")
                return redirect(url_for('auth.login'))

            if not hasattr(current_user, 'role') or current_user.role not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for('dashboard.home'))

            return f(*args, **kwargs)
        return decorated_function
    return wrapper
