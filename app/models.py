from datetime import datetime
from flask_login import UserMixin
from . import db  # or from app import db depending on your project

# Association table for host managing volunteers
host_volunteer = db.Table(
    'host_volunteer',
    db.Column('host_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('volunteer_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

# -------------------- User --------------------
class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), nullable=False, default='volunteer')
    gender = db.Column(db.String(20), default='Other')

    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    profile_pic = db.Column(db.String(200), nullable=True)

    current_badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=True)
    current_badge = db.relationship('Badge', foreign_keys=[current_badge_id])

    events = db.relationship('Event', backref='creator', lazy=True)
    bookings = db.relationship('Booking', backref='user', lazy=True)
    
    attendances = db.relationship('AttendanceRecord', backref='volunteer', lazy=True)

# 🔥 ADD THIS SEPARATELY
    user_badges = db.relationship('UserBadge', back_populates='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    goals = db.relationship('Goal', backref='user', lazy=True)
    feedbacks = db.relationship('Feedback', backref='user', lazy=True)
    impact_entries = db.relationship('ImpactEntry', backref='user', lazy=True)
    attendance_records = db.relationship('AttendanceRecord', backref='user', lazy=True)
    is_volunteer_active = db.Column(db.Boolean, default=True)
    total_hours = db.Column(db.Float, default=0.0)

    # 🔥 New: host-manages-volunteers relationship
    managed_volunteers = db.relationship(
        'User',
        secondary=host_volunteer,
        primaryjoin=(host_volunteer.c.host_id == id),
        secondaryjoin=(host_volunteer.c.volunteer_id == id),
        backref='managing_hosts'
    )

    @property
    def is_volunteer(self):
        return self.role == 'volunteer'

    @property
    def completed_task_count(self):
        return AttendanceRecord.query.filter_by(volunteer_id=self.id, task_completed=True).count()

    @property
    def total_hours(self):
        return round(sum(record.hours for record in self.attendances if record.status == 'present'), 2)

    # ✅ NEW: full_name property for convenience
    @property
    def full_name(self):
        return self.name


# -------------------- Event --------------------
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    thumbnail = db.Column(db.String(200), nullable=True)
    proof = db.Column(db.String(200), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    archived = db.Column(db.Boolean, default=False)
    passcode = db.Column(db.String(100), nullable=True)
    qr_code = db.Column(db.String(200), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50)) 
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)

    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    bookings = db.relationship('Booking', backref='event', lazy=True)
    attendances = db.relationship('AttendanceRecord', backref='event', lazy=True)
    feedbacks = db.relationship('Feedback', backref='event', lazy=True)
    xp_score = db.Column(db.Integer, default=10)  # ← இதை add பண்ணு
    duration = db.Column(db.Integer, default=1)    # ← இதையும் add பண்ணு (bulk upload use பண்றது)
    tags = db.Column(db.String(200), nullable=True) # ← இதையும்


# -------------------- Booking --------------------
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False, index=True)
    appointment_time = db.Column(db.DateTime, nullable=True)
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    checked_in = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(20), default='booked')
    check_in_time = db.Column(db.DateTime, nullable=True)
    task_start_time = db.Column(db.DateTime, nullable=True)
    completed_time = db.Column(db.DateTime, nullable=True)

    proof_image = db.Column(db.String(200), nullable=True)
    selfie_image = db.Column(db.String(200), nullable=True)

    xp_earned = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# -------------------- AttendanceRecord --------------------

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_record'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False, index=True)
    volunteer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    hours = db.Column(db.Float, nullable=False, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    check_in_time = db.Column(db.DateTime)
    check_out_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='present')

    checked_in = db.Column(db.Boolean, default=False)
    task_assigned = db.Column(db.Boolean, default=False)
    task_started = db.Column(db.Boolean, default=False)
    task_completed = db.Column(db.Boolean, default=False)
    xp = db.Column(db.Integer, default=0)

    @property
    def calculated_hours(self):
        if self.check_out_time:
            delta = self.check_out_time - self.timestamp
            return round(delta.total_seconds() / 3600, 2)
        return 0


# -------------------- Badge --------------------
class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    level = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    

    image_url = db.Column(db.String(256), nullable=True)

    # Badge unlock conditions
    condition_type = db.Column(db.String(50), nullable=True)  # e.g., 'Attend X Events'
    condition_value = db.Column(db.Integer, nullable=True)    # e.g., 3

    tags = db.Column(db.String(128), nullable=True)
    xp_reward = db.Column(db.Integer, nullable=True)

    # Foreign key to User
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Explicit relationship with foreign_keys specified
    creator = db.relationship('User', foreign_keys=[created_by])

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_badges = db.relationship('UserBadge', back_populates='badge', lazy=True)

    def __repr__(self):
        return f'<Badge {self.name}>'


# -------------------- UserBadge --------------------
# -------------------- UserBadge --------------------
class UserBadge(db.Model):
    __tablename__ = 'user_badge'

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=False)

    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress = db.Column(db.Integer, default=0)

    # ✅ FIXED RELATIONSHIPS (no backref conflict)
    user = db.relationship('User', back_populates='user_badges')
    badge = db.relationship('Badge', back_populates='user_badges')

# -------------------- Stat --------------------
class Stat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    value = db.Column(db.Integer, default=0)


# -------------------- Notification --------------------
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(50), default='info-circle')
    category = db.Column(db.String(50))  # 🔥 New
    related_event_id = db.Column(db.Integer, db.ForeignKey('event.id'))  # 🔥 New
    related_badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'))  # 🔥 New
    related_xp = db.Column(db.Integer)  # 🔥 New
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)


# -------------------- Goal --------------------

class Goal(db.Model):
    __tablename__ = 'goals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)

    deadline = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 🔥 IMPORTANT FIX
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    status = db.Column(db.String(20), default='Pending')  # Pending / Completed
    priority = db.Column(db.String(10), default='Low')    # Low / Medium / High

    progress = db.Column(db.Integer, default=0)  # 0–100 %

    tags = db.Column(db.Text, nullable=True)
    quote = db.Column(db.String(255), nullable=True)

    # 🚀 OPTIONAL (future ready features)
    completed_at = db.Column(db.DateTime, nullable=True)
    xp_reward = db.Column(db.Integer, default=0)

    # -------------------- HELPERS --------------------

    def get_tags(self):
        return [tag.strip() for tag in self.tags.split(',')] if self.tags else []

    def is_completed(self):
        return self.status == "Completed"

    def days_left(self):
        if self.deadline:
            return (self.deadline.date() - datetime.utcnow().date()).days
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "deadline": self.deadline.strftime("%Y-%m-%d") if self.deadline else None,
            "created_at": self.created_at.strftime("%Y-%m-%d") if self.created_at else None,
            "status": self.status,
            "priority": self.priority,
            "progress": self.progress,
            "tags": self.get_tags(),
            "quote": self.quote or "Stay consistent and committed!",
            "days_left": self.days_left(),
            "xp_reward": self.xp_reward
        }

    def __repr__(self):
        return f"<Goal {self.title} - {self.status}>"
        
# -------------------- GoalTask --------------------
class GoalTask(db.Model):
    __tablename__ = 'goal_task'

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey('goals.id'), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    xp_reward = db.Column(db.Integer, default=10)
    order = db.Column(db.Integer, default=1)
    
    # Progress/Verification fields
    status = db.Column(db.String(20), default='pending') # pending, uploaded, verified, completed
    proof_image = db.Column(db.String(200), nullable=True)
    ai_verified = db.Column(db.Boolean, default=False)
    ai_confidence = db.Column(db.Integer, nullable=True)
    ai_label = db.Column(db.String(50), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "xp_reward": self.xp_reward,
            "order": self.order,
            "status": self.status,
            "proof_image": self.proof_image,
            "ai_verified": self.ai_verified,
            "completed_at": self.completed_at.strftime("%Y-%m-%d %H:%M:%S") if self.completed_at else None
        }

    def __repr__(self):
        return f"<GoalTask {self.title} - {self.status}>"
# -------------------- Review --------------------
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reviewer_name = db.Column(db.String(100))
    text = db.Column(db.Text)
    rating = db.Column(db.Integer)
    tags = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------- ImpactEntry --------------------
class ImpactEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(120))
    description = db.Column(db.Text)
    type = db.Column(db.String(50))
    date = db.Column(db.DateTime, default=datetime.utcnow)
    xp = db.Column(db.Integer)
    badge = db.Column(db.String(120), nullable=True)
    level_up = db.Column(db.Boolean, default=False)


# -------------------- Feedback --------------------
class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Feedback {self.rating} by User {self.user_id}>"


# -------------------- VolunteerReview --------------------
class VolunteerReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    tags = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "name": self.name,
            "text": self.text,
            "rating": self.rating,
            "tags": [tag.strip() for tag in self.tags.split(",")] if self.tags else [],
            "timestamp": self.timestamp.strftime("%d %b %Y %I:%M %p"),
            "timestamp_raw": self.timestamp.isoformat()
        }


# -------------------- XPLog --------------------
class XPLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    xp = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(256))  # Optional
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------- UserXP --------------------
class UserXP(db.Model):
    __tablename__ = 'user_xp'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    total_points = db.Column(db.Integer, default=0)

    user = db.relationship('User', backref=db.backref('xp_total', uselist=False))


# -------------------- CheckIn --------------------
class CheckIn(db.Model):
    __tablename__ = 'checkin'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

    check_in_time = db.Column(db.DateTime, default=datetime.utcnow)
    check_out_time = db.Column(db.DateTime, nullable=True)
    attended = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='checkins', lazy=True)
    event = db.relationship('Event', backref='checkins', lazy=True)


# -------------------- Reward --------------------
class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    xp_required = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------- Task --------------------
class Task(db.Model):
    __tablename__ = 'task'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, default=1)  # Task 1,2,3...
    xp_reward = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_tasks = db.relationship('UserTask', backref='task', lazy=True)
    questions = db.relationship('TaskQuestion', backref='task', lazy=True)


# -------------------- UserTask --------------------
class UserTask(db.Model):
    __tablename__ = 'user_task'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

    status = db.Column(db.String(20), default='pending')  # pending/uploaded/verified/failed
    proof_image = db.Column(db.String(200), nullable=True)
    ai_verified = db.Column(db.Boolean, default=False)
    ai_confidence = db.Column(db.Float, default=0.0)
    ai_label = db.Column(db.String(100), nullable=True)
    xp_earned = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------- TaskQuestion --------------------
class TaskQuestion(db.Model):
    __tablename__ = 'task_question'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    question = db.Column(db.String(300), nullable=False)
    options = db.Column(db.Text, nullable=True)   # JSON: ["A","B","C","D"]
    correct_answer = db.Column(db.String(200), nullable=True)
    question_type = db.Column(db.String(20), default='mcq')  # mcq / text


# -------------------- UserTaskAnswer --------------------
class UserTaskAnswer(db.Model):
    __tablename__ = 'user_task_answer'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('task_question.id'), nullable=False)
    answer = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)