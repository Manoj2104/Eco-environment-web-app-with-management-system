from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit
from datetime import datetime
import os


from flask_compress import Compress

# -------------------- Extensions --------------------
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
compress = Compress()

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
    
    # 🏎️ Enable ULTRA FAST static file caching (1 year)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000 

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['QR_FOLDER'], exist_ok=True)

    # -------------------- Init Extensions --------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    socketio.init_app(app)
    compress.init_app(app)

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
    from app.models import Goal, Review, ImpactEntry, GoalTask, Event, Notification, User, AttendanceRecord
    from app.utils.badge_unlocker import check_and_unlock_badges
    from sqlalchemy import func
    import random
    import datetime

    @socketio.on('connect')
    def handle_connect(auth=None):
        if current_user.is_authenticated:
            from flask_socketio import join_room
            join_room(str(current_user.id))
            emit('connected', {
                "message": "Connected successfully",
                "unread_notifications": Notification.query.filter_by(user_id=current_user.id, read=False).count(),
                "ongoing_events": Event.query.filter(Event.status == 'ongoing').count(),
            }, room=str(current_user.id))
        else:
            print("Unauthenticated user tried to connect.")

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
            
            # Analytics update
            live_volunteer_count = User.query.filter_by(role='volunteer', is_active=True).count()
            emit('analytics_data', {
                'live_volunteer_count': live_volunteer_count
            }, broadcast=True)

    @socketio.on('get_goals')
    def handle_get_goals():
        if not current_user.is_authenticated:
            return
        goals = Goal.query.filter_by(user_id=current_user.id).all()
        result = []
        for g in goals:
            gd = g.to_dict()
            tasks = GoalTask.query.filter_by(goal_id=g.id).order_by(GoalTask.order).all()
            gd['tasks'] = [t.to_dict() for t in tasks]
            result.append(gd)
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

    @socketio.on("get_analytics_data")
    def handle_analytics():
        live_volunteer_count = User.query.filter_by(role='volunteer', is_active=True).count()
        now = datetime.datetime.utcnow()
        ongoing_events_count = Event.query.filter(Event.start_time <= now, Event.end_time >= now).count()
        avg_hours = db.session.query(func.avg(AttendanceRecord.hours)).scalar() or 0
        emit('analytics_data', {
            'live_volunteer_count': live_volunteer_count,
            'ongoing_events_count': ongoing_events_count,
            'avg_hours': round(avg_hours, 1)
        })




