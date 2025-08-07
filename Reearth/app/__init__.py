from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit
from datetime import datetime
import os


# -------------------- Extensions --------------------
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

# Live check-in tracker
checked_in_volunteers = {}

def create_app():
    app = Flask(__name__)

    # -------------------- Config --------------------
    app.config['SECRET_KEY'] = 'super-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///eco_nova.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join('app', 'static', 'uploads')
    app.config['QR_FOLDER'] = os.path.join('app', 'static', 'qr_codes')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['QR_FOLDER'], exist_ok=True)

    # -------------------- Init Extensions --------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    socketio.init_app(app)

    # -------------------- Blueprints --------------------
    from app.auth import auth as auth_blueprint
    from app.events import events as events_blueprint
    from app.badges import badges_bp as badges_blueprint
    from app.admin import admin as admin_blueprint
    from app.dashboard import dashboard as dashboard_blueprint
    from app.main import main as main_blueprint
    from app.booking import bookings as bookings_blueprint
    from app.routes.test import test_bp

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(events_blueprint)
    app.register_blueprint(badges_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(bookings_blueprint)
    app.register_blueprint(test_bp)

    # Register Socket.IO events
    register_socketio_handlers()

    return app

# -------------------- Socket.IO Events --------------------
def register_socketio_handlers():
    from flask import request
    from app.models import Goal, Review, ImpactEntry
    from app.utils.badge_unlocker import check_and_unlock_badges
    import random
    import datetime

    @socketio.on('check_in')
    def handle_check_in(data):
        volunteer_id = data.get('volunteer_id')
        if volunteer_id:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            checked_in_volunteers[volunteer_id] = now
            emit('update_status', {
                'volunteer_id': volunteer_id,
                'checked_in_at': now
            }, broadcast=True)

    @socketio.on('get_goals')
    def handle_get_goals():
        if not current_user.is_authenticated:
            return
        goals = Goal.query.filter_by(user_id=current_user.id).all()
        result = [{
            "title": g.title,
            "description": g.description,
            "deadline": g.deadline.strftime("%d %b, %Y") if g.deadline else "Sunday",
            "status": g.status,
            "priority": g.priority,
            "progress": g.progress or 0,
            "quote": g.quote or "Stay consistent and committed!",
            "tags": [tag.strip() for tag in g.tags.split(",")] if g.tags else []
        } for g in goals]
        emit("update_goals", result)

    @socketio.on("get_reviews")
    def handle_get_reviews():
        reviews = Review.query.order_by(Review.timestamp.desc()).all()
        result = [{
            "name": r.reviewer_name,
            "text": r.text,
            "rating": r.rating,
            "tags": [t.strip() for t in r.tags.split(",")] if r.tags else [],
            "timestamp": r.timestamp.strftime("%d %b %Y, %I:%M %p"),
            "timestamp_raw": r.timestamp.isoformat()
        } for r in reviews]
        emit("update_reviews", result)

    @socketio.on("submit_review")
    def handle_submit_review(data):
        review = Review(
            reviewer_name=data.get("name"),
            text=data.get("text"),
            rating=int(data.get("rating", 5)),
            tags=data.get("tags"),
            timestamp=datetime.datetime.utcnow()
        )
        db.session.add(review)
        db.session.commit()
        handle_get_reviews()

    @socketio.on("request_timeline")
    def handle_request_timeline():
        if not current_user.is_authenticated:
            return
        entries = ImpactEntry.query.filter_by(user_id=current_user.id).order_by(ImpactEntry.date.desc()).all()
        result = [{
            "title": e.title,
            "description": e.description,
            "type": e.type,
            "date": e.date.strftime("%Y-%m-%d"),
            "xp": e.xp,
            "badge": e.badge,
            "level_up": e.level_up
        } for e in entries]
        emit("receive_timeline", result)

    @socketio.on("get_feedback_summary")
    def handle_feedback_summary():
        summary = {
            "avg_rating": round(random.uniform(3.5, 5.0), 2),
            "total_responses": random.randint(50, 150),
            "positive_percent": random.randint(70, 95)
        }
        emit("feedback_stats", summary)

        breakdown = {
            "5_votes": random.randint(50, 100),
            "4_votes": random.randint(20, 60),
            "3_votes": random.randint(10, 30),
            "2_votes": random.randint(1, 10),
            "1_votes": random.randint(1, 5)
        }
        emit("rating_breakdown", breakdown)

        keywords = ["engaging", "fun", "inspiring", "interactive", "informative"]
        emit("feedback_keywords", keywords)

        today = datetime.date.today()
        labels = [(today - datetime.timedelta(days=i)).strftime("%d %b") for i in range(6, -1, -1)]
        values = [round(random.uniform(3.5, 5.0), 2) for _ in range(7)]
        emit("trend_data", {"labels": labels, "values": values})

    @socketio.on("task_completed")
    def handle_task_completed(data):
        if current_user.is_authenticated:
            check_and_unlock_badges(current_user)



from flask_socketio import join_room, emit
from flask_login import current_user
from app.models import Event, Notification

@socketio.on('connect')
def handle_connect(auth=None):
    if current_user.is_authenticated:
        join_room(str(current_user.id))
        emit('connected', {
            "message": "Connected successfully",
            "unread_notifications": Notification.query.filter_by(user_id=current_user.id, read=False).count(),
            "ongoing_events": Event.query.filter(Event.status == 'ongoing').count(),
        }, room=str(current_user.id))
    else:
        print("Unauthenticated user tried to connect.")


from flask_socketio import SocketIO, emit
from app.models import User, Event, AttendanceRecord
from app import db
from datetime import datetime
from sqlalchemy import func
# Global set to track live checked-in volunteer IDs
live_checked_in_volunteers = set()

@socketio.on('check_in')
def handle_check_in(data):
    volunteer_id = data.get('volunteer_id')
    if volunteer_id:
        # Add volunteer to live checked-in set
        live_checked_in_volunteers.add(volunteer_id)
        
        # You may want to update your AttendanceRecord checked_in status here in DB too
        attendance = AttendanceRecord.query.filter_by(volunteer_id=volunteer_id, checked_in=True).first()
        if not attendance:
            # Example: mark the volunteer as checked in in attendance record, or create one if needed
            # This part depends on your app logic
            pass
        
        # Emit updated live volunteer count to all clients
        emit('analytics_data', {
            'live_volunteer_count': len(live_checked_in_volunteers)
        }, broadcast=True)

@socketio.on('check_out')
def handle_check_out(data):
    volunteer_id = data.get('volunteer_id')
    if volunteer_id and volunteer_id in live_checked_in_volunteers:
        live_checked_in_volunteers.remove(volunteer_id)
        emit('analytics_data', {
            'live_volunteer_count': len(live_checked_in_volunteers)
        }, broadcast=True)

from flask_socketio import SocketIO, emit
from app import socketio, db
from app.models import User, Event, AttendanceRecord
from sqlalchemy import func
from datetime import datetime

@socketio.on('get_analytics_data')
def handle_analytics():
    live_volunteer_count = User.query.filter_by(role='volunteer', is_active=True).count()

    now = datetime.utcnow()
    ongoing_events_count = Event.query.filter(Event.start_time <= now, Event.end_time >= now).count()

    avg_hours = db.session.query(func.avg(AttendanceRecord.hours)).scalar() or 0
    avg_hours = round(avg_hours, 1)

    emit('analytics_data', {
        'live_volunteer_count': live_volunteer_count,
        'ongoing_events_count': ongoing_events_count,
        'avg_hours': avg_hours
    })




