from app.models import Badge, UserBadge, db, CheckIn
from flask_socketio import emit
from .notifications import create_notification

def check_and_unlock_badges(user):
    """Checks and unlocks badges based on tasks and check-ins."""
    unlocked = []
    
    # Check-in based badges
    checkin_count = CheckIn.query.filter_by(user_id=user.id).count()
    task_count = len(getattr(user, 'completed_tasks', [])) or 0
    
    unlocked_badge_ids = {b.badge_id for b in UserBadge.query.filter_by(user_id=user.id).all()}
    all_badges = Badge.query.all()
    
    for badge in all_badges:
        if badge.id in unlocked_badge_ids:
            continue
            
        is_eligible = False
        if badge.unlock_condition:
            if badge.unlock_condition.startswith("checkins:"):
                required = int(badge.unlock_condition.split(":")[1])
                if checkin_count >= required: is_eligible = True
            elif badge.unlock_condition.startswith("tasks:"):
                required = int(badge.unlock_condition.split(":")[1])
                if task_count >= required: is_eligible = True
                
        if is_eligible:
            new_ub = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(new_ub)
            unlocked.append(badge)

    if unlocked:
        db.session.commit()
        for b in unlocked:
            # 🔥 This will trigger the global sound via create_notification
            create_notification(
                user.id, 
                "🏅 Badge Earned!", 
                f"You've unlocked the '{b.name}' badge!", 
                icon="award", 
                category="badge",
                badge_id=b.id
            )
            
        emit('new_badge', {
            'badges': [{'name': b.name, 'icon': getattr(b, 'image_url', 'award'), 'desc': b.description} for b in unlocked]
        }, room=f"user_{user.id}")

    return [b.name for b in unlocked]
