from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import UserBadge

badge_bp = Blueprint('badges', __name__)

@badge_bp.route('/badges1')
@login_required
def badge_collection():
    user_badges = UserBadge.query.filter_by(user_id=current_user.id).all()
    return render_template('badge_collection.html', badges=[ub.badge for ub in user_badges])
