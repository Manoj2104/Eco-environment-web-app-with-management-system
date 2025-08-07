from app import db, create_app, socketio
app = create_app()
with app.app_context():
    db.create_all()
if __name__ == '__main__':
    socketio.run(app, debug=True, port=2105)
