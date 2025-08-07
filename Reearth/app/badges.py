from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Badge

badges_bp = Blueprint('badges', __name__)

@badges_bp.route('/badges')
@login_required
def view_badges():
    all_badges = Badge.query.all()
    earned_badges = current_user.badges if hasattr(current_user, 'badges') else []

    # Categorize
    badges = {
        'earned': earned_badges,
        'locked': [b for b in all_badges if b not in earned_badges]
    }

    return render_template('view_badges.html', badges=badges)
