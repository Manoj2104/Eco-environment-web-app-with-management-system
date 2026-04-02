from flask_socketio import emit, join_room
from flask_login import current_user
from datetime import datetime
from app import socketio
from app.models import db, Notification
from app.utils.badge_unlocker import check_and_unlock_badges


# 🔥 ADD THIS FUNCTION
def emit_full_user_update(user):
    xp_for_next = user.level * 100
    xp_percent = int((user.xp / xp_for_next) * 100)

    socketio.emit('user_full_update', {
        'xp': user.xp,
        'level': user.level,
        'xp_percent': xp_percent,
        'xp_for_next_level': xp_for_next,
        'next_level': user.level + 1,
        'xp_remaining': xp_for_next - user.xp,
        'tasks': user.tasks_completed,
        'events': user.events_joined,
        'hours': user.hours
    }, room=f"user_{user.id}")

# ✅ AUTO CONNECT (MOST IMPORTANT)
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        room = f"user_{current_user.id}"
        join_room(room)
        print(f"🔥 Connected & joined room: {room}")


# ✅ SOCKET JOIN ROOM
@socketio.on('join')
def handle_join(data):
    room = data.get('room') or f"user_{data.get('user_id')}"
    if room != "user_None":
        join_room(room)
        print(f"✅ Client joined room: {room}")


# ================= TASK COMPLETED =================
@socketio.on('task_completed')
def handle_task_completed(data):
    if not current_user.is_authenticated:
        return

    unlocked_badges = check_and_unlock_badges(current_user)

    if unlocked_badges:
        for badge in unlocked_badges:
            notif = Notification(
                user_id=current_user.id,
                title="🎉 Badge Unlocked!",
                message=f"You unlocked '{badge}' badge!",
                icon="award"
            )
            db.session.add(notif)

        db.session.commit()

        # 🔥 SEND NOTIFICATION
        emit('new_notification', {
            'title': '🎉 Badge Unlocked!',
            'message': f"You earned: {', '.join(unlocked_badges)}",
            'icon': 'award'
        }, room=f"user_{current_user.id}")

        # 🔥 UPDATE BADGE COUNT (REALTIME)
        emit('badge_update', {
            'count': len(unlocked_badges)
        }, room=f"user_{current_user.id}")

        # 🔥 ACTIVITY FEED
        emit('activity_update', {
            'text': f"Unlocked badges: {', '.join(unlocked_badges)}",
            'color': 'dot-purple'
        }, room=f"user_{current_user.id}")


# ================= CHECK-IN SUCCESS =================
@socketio.on('checkin_success')
def handle_checkin_success(data):
    if not current_user.is_authenticated:
        return

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

    # 🔥 NOTIFICATION
    emit('new_notification', {
        'title': notification.title,
        'message': notification.message,
        'icon': notification.icon,
        'timestamp': notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f"user_{current_user.id}")

    # 🔥 UPDATE EVENT COUNT
    emit('event_update', {
        'increment': 1
    }, room=f"user_{current_user.id}")

    # 🔥 ACTIVITY FEED
    emit('activity_update', {
        'text': f"Checked into {event_name}",
        'color': 'dot-green'
    }, room=f"user_{current_user.id}")



