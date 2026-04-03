import os
import traceback
import sys

try:
    from app import create_app, socketio, db

    # Initialize the Flask application
    app = create_app()

    # Ensure database tables are created (SQLite uses a local file)
    with app.app_context():
        db.create_all()
        print("Database initialized successfully.")

except Exception as e:
    print("FATAL ERROR DURING APP INITIALIZATION:")
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)

if __name__ == "__main__":
    # This block is used for local development
    port = int(os.environ.get("PORT", 2105))
    print(f"Starting server on port {port}...")
    socketio.run(app, host="0.0.0.0", port=port, debug=True)