from app import socketio
# utils/notifications.py
# utils/notifications.py
from app import db
from app.models import Notification
from datetime import datetime

def create_notification(user_id, title, message, icon='info-circle', category='general', event_id=None, badge_id=None, xp=None):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        icon=icon,
        category=category,
        related_event_id=event_id,
        related_badge_id=badge_id,
        related_xp=xp,
        timestamp=datetime.utcnow(),
        read=False
    )
    db.session.add(notification)
    try:
        db.session.commit()
        # 🔥 TRIGGER REAL-TIME SOUND + TOAST
        socketio.emit('new_notification', {
            'id': notification.id,
            'title': title,
            'message': message,
            'icon': icon,
            'timestamp': notification.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'category': category
        }, room=f"user_{user_id}")
    except Exception as e:
        db.session.rollback()
        print("Notification Error:", e)


def send_notification(title, message, icon="bi-info-circle", color="primary"):
    socketio.emit('new_notification', {
        "title": title,
        "message": message,
        "icon": icon,
        "color": color,
        "time": "just now"
    }, broadcast=True)


