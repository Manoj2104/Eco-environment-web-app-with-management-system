from app import socketio

def emit_user(user_id, event, data):
    socketio.emit(event, data, room=f"user_{user_id}")