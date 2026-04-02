from .models import Badge, UserBadge, Booking, Event, db
from flask_login import current_user

def check_and_award_badges(user):
    badges_awarded = []

    # Badge 1: First Step - First Event Created
    if len(user.events) >= 1:
        badge = Badge.query.filter_by(name='First Step').first()
        if badge and badge not in [b.badge for b in user.badges]:
            db.session.add(UserBadge(user_id=user.id, badge_id=badge.id))
            badges_awarded.append(badge.name)

    # Badge 2: Eco Explorer - 3 event bookings
    if len(user.bookings) >= 3:
        badge = Badge.query.filter_by(name='Eco Explorer').first()
        if badge and badge not in [b.badge for b in user.badges]:
            db.session.add(UserBadge(user_id=user.id, badge_id=badge.id))
            badges_awarded.append(badge.name)

    # Add more badge logic similarly...

    if badges_awarded:
        db.session.commit()
    
    return badges_awarded
