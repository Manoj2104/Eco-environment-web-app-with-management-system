from flask_socketio import SocketIO, emit, join_room
from flask_login import current_user
from datetime import datetime
from app.models import db, Notification
from utils.badge_unlocker import check_and_unlock_badges

socketio = SocketIO(cors_allowed_origins='*')

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")
        print(f"✅ User {user_id} joined room")

@socketio.on('task_completed')
def handle_task_completed(data):
    if current_user.is_authenticated:
        unlocked_badges = check_and_unlock_badges(current_user)
        if unlocked_badges:
            for badge in unlocked_badges:
                notif = Notification(
                    user_id=current_user.id,
                    title="🎉 Badge Unlocked!",
                    message=f"You unlocked the '{badge}' badge!",
                    icon="award"
                )
                db.session.add(notif)
            db.session.commit()

            emit('new_notification', {
                'title': '🎉 Badge Unlocked!',
                'message': f"You earned: {', '.join(unlocked_badges)}",
                'icon': 'award'
            }, room=f"user_{current_user.id}")


@socketio.on('checkin_success')
def handle_checkin_success(data):
    if current_user.is_authenticated:
        event_name = data.get('event_name', 'an event')

        notification = Notification(
            user_id=current_user.id,
            title="✅ Check-In Successful",
            message=f"You checked in to {event_name}.",
            icon="person-check-fill",
            timestamp=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()

        emit('new_notification', {
            'title': notification.title,
            'message': notification.message,
            'icon': notification.icon,
            'timestamp': notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }, room=f"user_{current_user.id}")
