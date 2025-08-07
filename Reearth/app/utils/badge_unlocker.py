from app.models import Badge, UserBadge, db
from flask_socketio import emit

def check_and_unlock_badges(user):
    task_count = len(user.completed_tasks)  # Replace with your actual task-completion logic
    unlocked = []

    criteria = {
        1: "Task Novice",
        5: "Task Achiever",
        10: "Task Master",
    }

    for required, badge_name in criteria.items():
        badge = Badge.query.filter_by(name=badge_name).first()
        if not badge:
            continue  # Skip if badge doesn't exist

        already_unlocked = UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first()
        if task_count >= required and not already_unlocked:
            new = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(new)
            unlocked.append(badge)

    if unlocked:
        db.session.commit()
        emit('new_badge', {
            'badges': [{'name': b.name, 'icon': b.image_url, 'desc': b.description} for b in unlocked]
        }, to=f"user_{user.id}")

from app.models import db, UserBadge, Badge, CheckIn
from flask_login import current_user

def check_and_unlock_badges(user_id):
    checkin_count = CheckIn.query.filter_by(user_id=user_id).count()
    unlocked_badge_ids = {b.badge_id for b in UserBadge.query.filter_by(user_id=user_id).all()}
    
    all_badges = Badge.query.all()
    for badge in all_badges:
        if badge.id in unlocked_badge_ids:
            continue

        if badge.unlock_condition.startswith("checkins:"):
            required = int(badge.unlock_condition.split(":")[1])
            if checkin_count >= required:
                new = UserBadge(user_id=user_id, badge_id=badge.id)
                db.session.add(new)
                db.session.commit()
