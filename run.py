import os
from app import create_app, socketio, db

# Initialize the Flask application
app = create_app()

# Ensure database tables are created (SQLite uses a local file)
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    # This block is used for local development
    port = int(os.environ.get("PORT", 2105))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)