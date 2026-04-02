from flask import Blueprint, jsonify
from flask_login import current_user
from app import socketio
from datetime import datetime

test_bp = Blueprint('test', __name__)

@test_bp.route('/send-test-notification')
def send_test_notification():
    # ⚠️ WARNING: This bypasses authentication!
    test_user_id = 1  # replace with a real user ID from your database

    notification_data = {
        'id': 99999,
        'title': 'Test Alert',
        'message': 'This is a real-time test notification!',
        'timestamp': datetime.utcnow().strftime('%b %d, %H:%M'),
        'icon': 'bell'
    }

    socketio.emit('new_notification', notification_data, to=f"user_{test_user_id}")
    return jsonify({'status': 'sent'})
