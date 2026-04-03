import eventlet
eventlet.monkey_patch()

import os
from app import create_app, socketio, db

app = create_app()

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 2105))
    socketio.run(app, host="0.0.0.0", port=port)