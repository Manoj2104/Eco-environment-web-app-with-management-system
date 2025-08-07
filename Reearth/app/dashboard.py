from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from .models import Event, UserBadge, Booking, Badge, User, AttendanceRecord, Notification
from app import db, socketio
from geopy.distance import geodesic
from pyzbar.pyzbar import decode
from PIL import Image
import io
from app.decorators import roles_required
from app.utils.decorators import roles_required
from werkzeug.security import generate_password_hash
import csv
from io import StringIO
import os
from .models import db, VolunteerReview  # <- Ensure this is imported where create_app is defined
from sqlalchemy import func
from werkzeug.utils import secure_filename
from flask_socketio import emit, join_room
from flask import request, render_template
import qrcode
from io import BytesIO
import base64
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from flask_socketio import emit
from datetime import datetime
from app import socketio, db
from app.models import ImpactEntry  # Adjust import if needed
from app.models import db, User, Reward 
from app.models import CheckIn

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Badge, UserBadge, AttendanceRecord, XPLog, UserXP, Event




dashboard = Blueprint('dashboard', __name__)

# Function to archive old events
def archive_expired_events():
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=45)
    expired_events = Event.query.filter(Event.date < cutoff, Event.archived == False).all()
    current_app.logger.info(f"Archiving {len(expired_events)} events older than {cutoff}")
    for event in expired_events:
        event.archived = True
    db.session.commit()

# Dashboard home route
@dashboard.route('/dashboard')
@login_required
def home():
    archive_expired_events()
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # Adjust timezone for your region

    all_events = Event.query.filter_by(archived=False).all()
    current_app.logger.info(f"Loaded {len(all_events)} active events")

    event_data = []
    try:
        user_loc = (float(current_user.latitude), float(current_user.longitude))
    except Exception as e:
        current_app.logger.warning(f"User location not available or invalid: {e}")
        user_loc = None

    for event in all_events:
        include_event = True
        if user_loc and event.latitude and event.longitude:
            try:
                distance_km = geodesic((event.latitude, event.longitude), user_loc).km
                include_event = distance_km <= 20
            except Exception as e:
                current_app.logger.warning(f"Distance calculation error: {e}")
                include_event = False

        if include_event:
            booking = Booking.query.filter_by(event_id=event.id, user_id=current_user.id).first()
            attendance = AttendanceRecord.query.filter_by(event_id=event.id, volunteer_id=current_user.id).first()

            status = {
                "booked": False,
                "checked_in": False,
                "task_started": False,
                "task_completed": False,
                "button_state": "join",
            }

            if booking:
                status["booked"] = True
                diff = (now - event.date).total_seconds()

                if attendance:
                    status["checked_in"] = True
                    if attendance.task_completed:
                        status["task_completed"] = True
                        status["button_state"] = "completed"
                    elif attendance.task_started:
                        status["task_started"] = True
                        status["button_state"] = "task"
                    else:
                        status["button_state"] = "checked_in"
                else:
                    if diff < -1800:
                        status["button_state"] = "booked"
                    elif -1800 <= diff < 0:
                        status["button_state"] = "countdown"
                    elif 0 <= diff <= 900:
                        status["button_state"] = "checkin"
                    elif 900 < diff <= 1500:
                        status["button_state"] = "last_checkin"
                    else:
                        status["button_state"] = "missed"

            event_data.append({"event": event, "status": status})

    return render_template('dashboard.html',
                           user=current_user,
                           events=event_data,
                           current_time=now,
                           timedelta=timedelta)


# Update volunteer location route
@dashboard.route('/update_location', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()
    current_app.logger.info(f"Location update received: {data}")
    try:
        current_user.latitude = float(data['latitude'])
        current_user.longitude = float(data['longitude'])
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        current_app.logger.error(f"Failed to update location: {e}")
        return jsonify({'status': 'error'}), 400


# Book event route (unique endpoint name)
@dashboard.route('/book_event/<int:event_id>', methods=['POST'])
@login_required
def book_event(event_id):
    event = Event.query.get(event_id)
    if not event:
        current_app.logger.warning(f"Book event failed: Event {event_id} not found")
        return jsonify(success=False, message="Event not found")

    existing = Booking.query.filter_by(user_id=current_user.id, event_id=event_id).first()
    if existing:
        return jsonify(success=False, message="Already booked")

    booking = Booking(user_id=current_user.id, event_id=event_id, status='booked')
    db.session.add(booking)
    db.session.commit()
    return jsonify(success=True)



# ... Other routes like start_task, submit_task, profile, notifications etc. remain as you provided ...

# ------------------ SocketIO Handlers ------------------



# If you have another function named book_event, rename it like this:

@dashboard.route('/book_event_alt')
@login_required
def book_event_alt():
    # Your alternate booking-related logic here
    return jsonify(success=True, message="This is the alternate book_event route.")

@dashboard.route('/verify-checkin-alt', methods=['POST'])
@login_required
def verify_checkin_alt():
    # Your existing logic here
    event_id = request.form.get('event_id')
    event = Event.query.get_or_404(event_id)

    input_passcode = request.form.get('passcode')
    if input_passcode and event.passcode and input_passcode.strip() == event.passcode.strip():
        return _process_checkin(event, method="passcode")

    qr_file = request.files.get('qr')
    if qr_file:
        try:
            img = Image.open(io.BytesIO(qr_file.read()))
            decoded = decode(img)
            if decoded:
                qr_text = decoded[0].data.decode('utf-8').strip()
                if qr_text == event.passcode.strip():
                    return _process_checkin(event, method="qr")
        except Exception as e:
            current_app.logger.error(f"QR decode error: {e}")

    return jsonify({'success': False, 'message': 'Invalid passcode or QR'})

def _process_checkin(event, method="passcode"):
    existing = AttendanceRecord.query.filter_by(event_id=event.id, volunteer_id=current_user.id).first()
    if existing:
        return jsonify({'success': False, 'message': 'Already checked in'})

    new_attendance = AttendanceRecord(
        event_id=event.id,
        volunteer_id=current_user.id,
        timestamp=datetime.utcnow(),
        status='present',
        task_assigned=True
    )
    db.session.add(new_attendance)
    db.session.commit()
    current_app.logger.info(f"User {current_user.id} checked in for event {event.id} via {method}")
    return jsonify({'success': True, 'method': method})

@dashboard.route('/start-task/<int:event_id>', methods=['POST'])
@login_required
def start_task(event_id):
    record = AttendanceRecord.query.filter_by(event_id=event_id, volunteer_id=current_user.id).first()
    if not record or not record.task_assigned:
        return jsonify({'success': False, 'message': 'You must check in first.'})

    now = datetime.utcnow()
    if record.timestamp and (now - record.timestamp).total_seconds() < 15:
        return jsonify({'success': False, 'message': 'Wait 15 seconds after check-in.'})

    if record.task_started:
        return jsonify({'success': False, 'message': 'Task already started.'})

    record.task_started = True
    record.task_start_time = now
    db.session.commit()
    current_app.logger.info(f"User {current_user.id} started task for event {event_id}")
    return jsonify({'success': True, 'message': 'Task started!'})

@dashboard.route('/submit-task/<int:event_id>', methods=['POST'])
@login_required
def submit_task(event_id):
    record = AttendanceRecord.query.filter_by(event_id=event_id, volunteer_id=current_user.id).first()
    if not record or not record.task_started:
        return jsonify({'success': False, 'message': 'Task not started yet.'})

    record.task_completed = True
    record.task_completed_time = datetime.utcnow()
    db.session.commit()
    current_app.logger.info(f"User {current_user.id} submitted task for event {event_id}")
    return jsonify({'success': True, 'message': 'Task submitted successfully!'})

@dashboard.route('/update-status-timers', methods=['POST'])
@login_required
def update_status_timers():
    now = datetime.utcnow()
    bookings = Booking.query.filter_by(user_id=current_user.id).all()

    updated = 0
    for booking in bookings:
        event = booking.event
        if not event or event.archived:
            continue

        start_time = event.date
        checkin_limit = start_time + timedelta(minutes=15)
        last_checkin_limit = start_time + timedelta(minutes=25)

        if booking.status == 'booked':
            if now > checkin_limit and now <= last_checkin_limit:
                booking.status = 'last_checkin'
                updated += 1
            elif now > last_checkin_limit:
                booking.status = 'missed'
                updated += 1
        elif booking.status == 'last_checkin' and now > last_checkin_limit:
            booking.status = 'missed'
            updated += 1

    db.session.commit()
    current_app.logger.info(f"Updated booking statuses: {updated}")
    return jsonify({'status': 'success', 'updated': updated})

from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import User, UserBadge, XPLog, AttendanceRecord, Badge



# -------------------- XP Progress Calculation --------------------
def calculate_xp_progress(user_id):
    user = User.query.get(user_id)
    current_xp = user.xp or 0
    current_level = user.level or 1
    xp_for_next_level = (current_level + 1) * 100  # Simple XP leveling logic
    progress_percent = min(100, int((current_xp / xp_for_next_level) * 100))

    return {
        "current_xp": current_xp,
        "current_level": current_level,
        "xp_for_next_level": xp_for_next_level,
        "progress_percent": progress_percent
    }

# -------------------- Attendance Page --------------------
@dashboard.route('/volunteer/attendance')
@login_required
def view_attendance():
    user_id = current_user.id
    attendance = AttendanceRecord.query.filter_by(volunteer_id=user_id).all()
    return render_template('dashboard/attendance.html', attendance=attendance)

# -------------------- Profile Page --------------------
from flask import render_template
from flask_login import login_required, current_user
from app.models import Badge, XPLog, UserBadge, User, AttendanceRecord
from datetime import datetime
from collections import defaultdict
from collections import defaultdict


from collections import defaultdict
from flask_login import login_required, current_user
from flask import render_template
from app.models import User, UserBadge, XPLog, AttendanceRecord

@dashboard.route("/profile")
@login_required
def profile():
    user_id = current_user.id

    # ✅ Earned badges
    earned_badges = UserBadge.query.filter_by(user_id=user_id).all()

    # ✅ XP Progress
    user = User.query.get(user_id)
    current_xp = user.xp or 0
    current_level = user.level or 1
    xp_for_next_level = (current_level + 1) * 100
    progress_percent = min(100, int((current_xp / xp_for_next_level) * 100))
    progress = {
        "current_xp": current_xp,
        "current_level": current_level,
        "xp_for_next_level": xp_for_next_level,
        "progress_percent": progress_percent
    }

    # ✅ XP logs
    xp_logs = XPLog.query.filter_by(user_id=user_id).order_by(XPLog.timestamp.asc()).all()
    xp_labels = [log.timestamp.strftime("%Y-%m-%d") for log in xp_logs]
    xp_values = [log.amount for log in xp_logs]
    xp_data = xp_logs  # ✅ Fix: assign xp_data

    # ✅ Monthly XP
    monthly_xp = defaultdict(int)
    for log in xp_logs:
        month_str = log.timestamp.strftime("%Y-%m")
        monthly_xp[month_str] += log.amount
    monthly_xp_labels = list(monthly_xp.keys())
    monthly_xp_data = list(monthly_xp.values())

    # ✅ Attendance
    attendance_records = AttendanceRecord.query.filter_by(volunteer_id=user_id).all()
    volunteer_hours_by_date = defaultdict(int)
    for record in attendance_records:
        if record.timestamp:
            date_str = record.timestamp.strftime("%Y-%m-%d")
            volunteer_hours_by_date[date_str] += 1
    volunteer_hours_labels = list(volunteer_hours_by_date.keys())
    volunteer_hours_values = list(volunteer_hours_by_date.values())
    volunteer_hours_data = {
        "labels": volunteer_hours_labels,
        "values": volunteer_hours_values
    }

    # ✅ Badge stats
    badge_counts = defaultdict(int)
    for badge in earned_badges:
        badge_counts[badge.badge.name] += 1
    badge_labels = list(badge_counts.keys())
    badge_data = list(badge_counts.values())

    # ✅ Total achievements
    

    # ✅ Activity logs
    activities = XPLog.query.filter_by(user_id=user_id).order_by(XPLog.timestamp.desc()).limit(10).all()

    # ✅ Dummy placeholder if needed
    event_participation_labels = []
    event_participation_data = []

    return render_template(
        "profile.html",
        user=current_user,
        earned_badges=earned_badges,
        progress=progress,
        xp_labels=xp_labels,
        xp_data=xp_data,
        xp_values=xp_values,
        monthly_xp_labels=monthly_xp_labels,
        monthly_xp_data=monthly_xp_data,
        volunteer_hours_labels=volunteer_hours_labels,
        volunteer_hours_data=volunteer_hours_data,
        event_participation_labels=event_participation_labels,
        event_participation_data=event_participation_data,
        badge_labels=badge_labels,
        badge_data=badge_data,
       
        activities=activities
    )





@dashboard.route('/xp-progress')
@login_required
def xp_progress():
    # Sample logic – you can customize this
    from flask import jsonify
    return render_template("xp_progress.html", user=current_user)

from datetime import datetime


@dashboard.route('/my-bookings')
@login_required
def my_bookings():
    now = datetime.utcnow()
    bookings = Booking.query.filter_by(user_id=current_user.id).all()

    upcoming_bookings = []
    past_bookings = []

    for booking in bookings:
        event_end_time = booking.event.date + timedelta(hours=2)
        if event_end_time < now:
            past_bookings.append(booking)
        else:
            upcoming_bookings.append(booking)

    return render_template('bookings.html', upcoming_bookings=upcoming_bookings, past_bookings=past_bookings, now=now)



@dashboard.route('/my-attendance')
@login_required
def my_attendance():
    records = AttendanceRecord.query.filter_by(volunteer_id=current_user.id).join(Event).order_by(AttendanceRecord.timestamp.desc()).all()
    return render_template('my_attendance.html', records=records)

@dashboard.route('/history')
@login_required
def history():
    archive_expired_events()
    created = Event.query.filter_by(creator_id=current_user.id, archived=True).all()
    bookings = Booking.query.filter_by(user_id=current_user.id).all()

    history_records = []

    for e in created:
        history_records.append({
            'title': e.title,
            'type': 'created',
            'date': e.date,
            'location': e.location,
            'status': 'past',
            'timestamp': e.date,
            'action': 'You hosted this event.'
        })

    for b in bookings:
        if b.event and b.event.archived:
            history_records.append({
                'title': b.event.title,
                'type': 'booked',
                'date': b.event.date,
                'location': b.event.location,
                'status': 'past',
                'timestamp': b.timestamp,
                'action': 'You booked this event.'
            })

    history_records.sort(key=lambda x: x['timestamp'], reverse=True)
    return render_template('history.html', history_records=history_records)

@dashboard.route('/see-volunteers')
@login_required
def see_volunteers():
    events = Event.query.filter_by(creator_id=current_user.id).all()
    event_ids = [event.id for event in events]
    bookings = Booking.query.filter(Booking.event_id.in_(event_ids)).all()
    volunteer_ids = list(set([b.user_id for b in bookings]))
    volunteers = User.query.filter(User.id.in_(volunteer_ids)).all()
    return render_template('see_volunteers.html', volunteers=volunteers)

@dashboard.route('/volunteer_profile/<int:user_id>')
@login_required
def view_volunteer_profile(user_id):
    volunteer = User.query.get_or_404(user_id)
    events_attended = AttendanceRecord.query.filter_by(volunteer_id=user_id).join(Event).order_by(AttendanceRecord.timestamp.desc()).all()
    earned_badges = db.session.query(UserBadge, Badge).join(Badge).filter(UserBadge.user_id == user_id).all()

    return render_template('volunteer_profile.html',
                           volunteer=volunteer,
                           events_attended=events_attended,
                           earned_badges=earned_badges)









from flask import Blueprint, send_file
from flask_login import login_required
from datetime import datetime, timedelta
from io import BytesIO

bookings = Blueprint('bookings', __name__)

@bookings.route('/add_to_calendar/<int:booking_id>')
@login_required
def add_to_calendar(booking_id):
    # TODO: Fetch booking and event info from your DB here using booking_id
    # Here’s a simple demo ics event for the example:

    event_title = "EcoNova Event"
    event_location = "Community Park"
    event_description = "Join us to clean the park and make a difference!"
    start = datetime.utcnow() + timedelta(days=1)  # Demo: event is tomorrow
    end = start + timedelta(hours=2)

    dtstamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    dtstart = start.strftime('%Y%m%dT%H%M%SZ')
    dtend = end.strftime('%Y%m%dT%H%M%SZ')

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//EcoNova//EcoNova Events//EN
BEGIN:VEVENT
UID:{booking_id}@econova.app
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{event_title}
DESCRIPTION:{event_description}
LOCATION:{event_location}
END:VEVENT
END:VCALENDAR
"""

    return send_file(BytesIO(ics_content.encode('utf-8')),
                     as_attachment=True,
                     download_name=f"{event_title.replace(' ', '_')}.ics",
                     mimetype='text/calendar')


@dashboard.route('/attendance-report')
@login_required
def attendance_report():
    # Your logic here, e.g., render a report template
    return render_template('host/attendance_report.html')

@dashboard.route('/event-stats')
@login_required
def event_stats():
    from sqlalchemy import func

    total_events = Event.query.count()
    attended_events = AttendanceRecord.query.filter_by(volunteer_id=current_user.id).count()
    hosted_events = Event.query.filter_by(creator_id=current_user.id).count()

    top_locations = db.session.query(
        Event.location, func.count().label('count')
    ).group_by(Event.location).order_by(func.count().desc()).limit(3).all()
    top_locations = [loc[0] for loc in top_locations]

    total_xp = getattr(current_user, 'total_xp', 0)
    highest_xp = db.session.query(func.max(AttendanceRecord.xp)).filter_by(volunteer_id=current_user.id).scalar() or 0
    earned_badges = db.session.query(UserBadge).filter_by(user_id=current_user.id).count()

    monthly_participation = db.session.query(
        func.strftime('%Y-%m', AttendanceRecord.timestamp), func.count()
    ).filter_by(volunteer_id=current_user.id).group_by(func.strftime('%Y-%m', AttendanceRecord.timestamp)).all()
    attendance_months = [m[0] for m in monthly_participation]
    attendance_values = [m[1] for m in monthly_participation]

    popular_categories = db.session.query(
        Event.category, func.count()
    ).group_by(Event.category).order_by(func.count().desc()).limit(5).all()
    category_labels = [c[0] for c in popular_categories]
    category_counts = [c[1] for c in popular_categories]

    total_checkins = AttendanceRecord.query.filter_by(volunteer_id=current_user.id).count()
    completed_tasks = AttendanceRecord.query.filter_by(volunteer_id=current_user.id, task_completed=True).count()
    completion_rate = round((completed_tasks / total_checkins) * 100, 1) if total_checkins else 0

    total_volunteers = User.query.count()

    top_attended_events = db.session.query(
        Event.title, func.count(AttendanceRecord.id)
    ).join(AttendanceRecord).filter(
        AttendanceRecord.volunteer_id == current_user.id
    ).group_by(Event.title).order_by(func.count().desc()).limit(5).all()

    # ✅ Do zip in Python
    event_data_zipped = list(zip(
        [t[0] for t in top_attended_events],
        [t[1] for t in top_attended_events]
    ))

    top_volunteers = db.session.query(
        User.name, func.sum(AttendanceRecord.xp)
    ).join(AttendanceRecord, AttendanceRecord.volunteer_id == User.id
    ).group_by(User.id).order_by(func.sum(AttendanceRecord.xp).desc()).limit(5).all()

    stats = {
        'total_events': total_events,
        'attended_events': attended_events,
        'hosted_events': hosted_events,
        'top_locations': top_locations,
        'total_xp': total_xp,
        'highest_xp': highest_xp,
        'earned_badges': earned_badges,
        'attendance_months': attendance_months,
        'attendance_values': attendance_values,
        'category_labels': category_labels,
        'category_counts': category_counts,
        'completion_rate': completion_rate,
        'total_volunteers': total_volunteers,
        'event_data_zipped': event_data_zipped,
        'top_volunteers': [{'name': v[0], 'xp': v[1]} for v in top_volunteers]
    }

    return render_template('dashboard/event_stats.html', stats=stats)




@dashboard.route('/upload-gallery')
@login_required
def upload_gallery():
    return render_template('dashboard/upload_gallery.html')


@dashboard.route('/event-feedback')
@login_required
def event_feedback():
    return render_template('dashboard/event_feedback.html')


@dashboard.route('/leaderboard')
@login_required
def leaderboard():
    top_users = User.query.order_by(User.xp.desc()).limit(10).all()  # or any logic you prefer
    return render_template('leaderboard.html', top_users=top_users)


@dashboard.route('/upload_selfie', methods=['GET', 'POST'])
@login_required
def upload_selfie():
    if request.method == 'POST':
        file = request.files.get('selfie')
        if file:
            filename = secure_filename(file.filename)
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
            flash('Selfie uploaded successfully!', 'success')
            return redirect(url_for('dashboard.profile'))
    return render_template('upload_selfie.html')

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from app import db
from app.forms import EditProfileForm


@dashboard.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.email = form.email.data
        current_user.bio = form.bio.data
        current_user.location = form.location.data
        current_user.instagram = form.instagram.data

        profile_pic = form.profile_pic.data
        if profile_pic:
            filename = secure_filename(profile_pic.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            profile_pic.save(upload_path)
            current_user.profile_pic = filename

        db.session.commit()
        flash("✅ Profile updated successfully!", "success")
        return redirect(url_for('dashboard.profile'))

    return render_template('edit_profile.html', form=form, user=current_user)





@dashboard.route('/notifications')
@login_required
def view_notifications():
    filter_by = request.args.get('filter')
    if filter_by == 'unread':
        notes = Notification.query.filter_by(user_id=current_user.id, read=False).order_by(Notification.timestamp.desc()).all()
    else:
        notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
    return render_template('notifications.html', notifications=notes)


@dashboard.route('/notifications/view/<int:note_id>')
@login_required
def view_notification(note_id):
    note = Notification.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        return redirect(url_for('dashboard.view_notifications'))
    note.read = True
    db.session.commit()
    return redirect(url_for('dashboard.view_notifications'))




def push_notification(title, message, role='Volunteer', icon='info-circle'):
    users = User.query.filter_by(role=role).all()
    for user in users:
        note = Notification(user_id=user.id, title=title, message=message, icon=icon)
        db.session.add(note)
    db.session.commit()

    # Emit via SocketIO
    from app import socketio
    for user in users:
        socketio.emit('new_notification', {
            'id': user.id,
            'title': title,
            'message': message,
            'timestamp': datetime.utcnow().strftime('%d %b %Y'),
            'icon': icon
        }, to=f'user_{user.id}')


@dashboard.route('/achievements')
@login_required
def achievements():
    earned_badges = db.session.query(UserBadge, Badge).join(Badge).filter(UserBadge.user_id == current_user.id).all()
    summary = {
        "events": len(current_user.events) if hasattr(current_user, 'events') else 0,
        "hours": AttendanceRecord.query.filter_by(volunteer_id=current_user.id).count() * 2,
        "tasks": AttendanceRecord.query.filter_by(volunteer_id=current_user.id, task_completed=True).count()
    }

    xp = getattr(current_user, 'xp', 0)
    level = xp // 100 + 1
    xp_progress = xp % 100

    return render_template('achievements.html',
                           user=current_user,
                           earned_badges=earned_badges,
                           summary=summary,
                           level=level,
                           xp_progress=xp_progress)



@dashboard.route("/calendar")
@login_required
def calendar():
    upcoming_events = Event.query.filter(Event.date >= datetime.utcnow()).order_by(Event.date.asc()).all()
    return render_template("event_calendar.html", upcoming_events=upcoming_events, now=datetime.now())



@dashboard.route('/qr-download')
@login_required
def qr_download():
    return render_template('qr_download.html')  # You can create this HTML file next

@dashboard.route('/language')
@login_required
def language():
    return render_template('language.html')


@dashboard.route('/checkin-dashboard')
@login_required
def checkin_dashboard():
    now = datetime.now()
    return render_template('checkin_dashboard.html', now=now)

@dashboard.route('/generate-certificates')
@login_required
def generate_certificates():
    # Dummy data – replace with real participants from DB
    participants = [
        {"name": "Manoj S", "event": "Tree Plantation Drive", "hours": 5},
        {"name": "Divya P", "event": "Beach Cleanup", "hours": 3},
        {"name": "Ravi K", "event": "Awareness Campaign", "hours": 2},
    ]
    return render_template('generate_certificates.html', participants=participants)

@dashboard.route('/download-certificate')
@login_required
def download_certificate():
    path = os.path.join(current_app.root_path, 'static', 'certificates', f'{current_user.id}_certificate.pdf')
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    else:
        return "Certificate not available yet", 404


from app import socketio
from flask_socketio import emit
from datetime import datetime

@dashboard.route('/award_badge')
@login_required
def award_badge():
    # Your logic
    ...
    db.session.commit()

    socketio.emit('new_notification', {
        'title': 'New Badge Earned!',
        'message': 'You unlocked the Eco Champion badge!',
        'icon': 'award',
        'timestamp': datetime.now().strftime('%d %b %Y')
    }, to=None)  # ✅ Fixed

    return redirect(url_for('dashboard.profile'))
from flask_socketio import join_room
from flask import request




@dashboard.route('/test_notify')
@login_required
def test_notify():
    from datetime import datetime
    from app import socketio
    from .models import Notification
    from app import db

    note = Notification(
        user_id=current_user.id,
        title="Test Notification",
        message="This is a real-time test message!",
        icon="bell"
    )
    db.session.add(note)
    db.session.commit()

    socketio.emit('new_notification', {
        'id': note.id,
        'title': note.title,
        'message': note.message,
        'timestamp': datetime.utcnow().strftime('%d %b %Y'),
        'icon': note.icon
    }, to=f"user_{current_user.id}")

    return "✅ Sent"

@dashboard.route('/realtime-attendance')
@login_required
def realtime_attendance():
    users = User.query.all()
    results = []

    for user in users:
        attendance = AttendanceRecord.query.filter_by(volunteer_id=user.id).order_by(AttendanceRecord.timestamp.desc()).first()
        results.append({
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'avatar': user.avatar_url if hasattr(user, 'avatar_url') else '/static/img/default.png',
            'checked_in': bool(attendance),
            'checkin_time': attendance.timestamp.strftime('%I:%M %p') if attendance else None
        })

    return jsonify(results)



@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        current_app.logger.info(f"User joined room: {room}")


@socketio.on('checkin')
def handle_checkin(data):
    name = data.get('name')
    user = User.query.filter_by(name=name).first()

    if user:
        # Prevent duplicate check-in
        existing = AttendanceRecord.query.filter_by(volunteer_id=user.id).first()
        if not existing:
            record = AttendanceRecord(
                volunteer_id=user.id,
                event_id=None,
                timestamp=datetime.utcnow(),
                status='present',
                task_assigned=False
            )
            db.session.add(record)
            db.session.commit()

        # Broadcast to all
        emit('new_checkin', {
            'id': user.id,
            'name': user.name,
            'time': datetime.utcnow().strftime('%I:%M %p')
        }, broadcast=True)


@dashboard.route('/certificates/export')
def export_csv():
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Name', 'Event', 'Hours'])

    for p in participants:
        cw.writerow([p.name, p.event, p.hours])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=certificates.csv"
    output.headers["Content-type"] = "text/csv"
    return output

from flask import render_template, request
from flask_login import login_required
from datetime import datetime
from app.models import db, User, Event, AttendanceRecord
from app.dashboard import dashboard

from flask_login import current_user
from datetime import datetime

from flask import render_template, request
from datetime import datetime
from app.models import Event, AttendanceRecord, User  # adjust imports to your models
from flask_login import login_required

from flask import request, render_template
from flask_login import current_user
from datetime import datetime
from app.models import User, Event, AttendanceRecord
from app import db

@dashboard.route('/certificates')
@login_required
def certificates():
    selected_event = request.args.get('event', None)

    # Query AttendanceRecords for the current user with joins
    query = (
        db.session.query(AttendanceRecord)
        .join(User, AttendanceRecord.volunteer_id == User.id)
        .join(Event, AttendanceRecord.event_id == Event.id)
        .filter(AttendanceRecord.volunteer_id == current_user.id)
    )

    if selected_event:
        query = query.filter(Event.title == selected_event)

    attendance_records = query.all()

    participants = []
    for record in attendance_records:
        participants.append({
            'name': record.volunteer.name,
            'event': record.event.title,
            'hours': record.hours  # Access property here
        })

    events = Event.query.all()

    return render_template(
        'certificates.html',
        participants=participants,
        events=events,
        selected_event=selected_event,
        now=datetime.now()
    )









@dashboard.route('/preview-certificate')
def preview_certificate():
    name = request.args.get('name')
    event = request.args.get('event')

    if not name or not event:
        return "Missing data", 400

    # Generate QR Code
    qr = qrcode.make(f"Certificate for {name} in {event}")
    qr_io = BytesIO()
    qr.save(qr_io, format='PNG')
    qr_io.seek(0)
    qr_base64 = "data:image/png;base64," + base64.b64encode(qr_io.read()).decode()

    # Render HTML with embedded QR
    return render_template('certificate_preview.html', name=name, event=event, qr_image=qr_base64)

from flask import render_template
from flask_login import login_required, current_user
from app.models import Goal
from app.dashboard import dashboard

@dashboard.route('/weekly-goals')
@login_required
def weekly_goals():
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.deadline.asc()).all()

    formatted_goals = []
    for g in goals:
        formatted_goals.append({
            "title": g.title,
            "description": g.description,
            "deadline": g.deadline.strftime("%d %b, %Y") if g.deadline else "No Deadline",
            "status": g.status,
            "priority": g.priority,
            "progress": g.progress if hasattr(g, "progress") else 0,
            "quote": g.quote or "💬 Stay consistent and committed!",
            "tags": [tag.strip() for tag in g.tags.split(',')] if g.tags else []
        })

    return render_template("volunteer/weekly_goals.html", goals=formatted_goals)



@dashboard.route('/reviews')
@login_required
def reviews():
    sample_reviews = [
        {
            'name': 'Anjali R.',
            'text': 'Loved volunteering at the community garden!',
            'rating': 5,
            'timestamp': '2 days ago',
            'tags': ['garden', 'teamwork']
        },
        {
            'name': 'Rahul M.',
            'text': 'Beach cleanup was an amazing experience.',
            'rating': 4,
            'timestamp': '5 days ago',
            'tags': ['cleanup', 'outdoor']
        },
        {
            'name': 'Neha K.',
            'text': 'Felt proud contributing to the blood donation camp.',
            'rating': 5,
            'timestamp': '1 week ago',
            'tags': ['donation']
        }
    ]
    return render_template('reviews.html', reviews=sample_reviews)

@dashboard.route('/reward-store')
@login_required
def reward_store():
    rewards = [
        {'name': 'EcoNova T-Shirt', 'description': 'Soft cotton t-shirt with logo', 'cost': 150},
        {'name': 'Reusable Water Bottle', 'description': 'Eco-friendly and stylish!', 'cost': 100},
        {'name': 'Exclusive Profile Badge', 'description': 'Showcase your impact.', 'cost': 50},
        {'name': 'Digital Certificate Upgrade', 'cost': 80},
        {'name': 'Event Early Access', 'cost': 120}
    ]
    return render_template('reward_store.html', rewards=rewards)



# app/dashboard.py

from flask import render_template
from flask_login import login_required
from .models import AttendanceRecord, Event


@dashboard.route('/certificates', endpoint='my_certificates')
@login_required
def certificates_page():
    all_events = db.session.query(
        AttendanceRecord.event_id,
        Event.title.label("event_name")
    ).join(Event).distinct().all()

    return render_template('certificates.html', events=all_events)



@dashboard.route('/impact-timeline', endpoint='impact_timeline')
@login_required
def impact_timeline():
    # Sample data or render as needed
    return render_template('impact_timeline.html')



@dashboard.route('/help-center', endpoint='help_center')
@login_required
def help_center():
    return render_template('help_center.html')

@dashboard.route('/xp-progress')
@login_required
def xp_progress_view():  # ✅ Changed from xp_progress to xp_progress_view to avoid conflict
    xp_labels = ["Jan", "Feb", "Mar", "Apr"]
    xp_history = [20, 50, 80, 110]
    current_xp = 110
    current_level = 2
    next_level = 3
    xp_required = 150
    xp_remaining = xp_required - current_xp
    xp_percent = round((current_xp / xp_required) * 100)

    milestones = [
        {"title": "Reached Level 1", "date": "2024-12-01"},
        {"title": "Earned 100 XP", "date": "2025-02-15"},
        {"title": "Completed 5 Events", "date": "2025-05-20"},
    ]

    return render_template(
        "xp_progress.html",
        xp_labels=xp_labels,
        xp_history=xp_history,
        current_xp=current_xp,
        current_level=current_level,
        next_level=next_level,
        xp_remaining=xp_remaining,
        xp_percent=xp_percent,
        milestones=milestones
    )


@dashboard.route('/download-xp-report')
@login_required
def download_xp_report():
    # Generate and send a report (e.g., PDF or CSV)
    return send_file('static/sample_xp_report.pdf', as_attachment=True)




from flask_socketio import emit
from math import floor
from app import socketio, db
from app.models import User

@socketio.on('request_leaderboard')
def handle_leaderboard_request():
    leaderboard_data = (
        db.session.query(User.name, User.xp)
        .order_by(User.xp.desc())
        .limit(10)
        .all()
    )

    leaderboard_list = [
        {'name': user.name, 'xp': user.xp, 'level': floor(user.xp / 100)}  # Calculate level dynamically
        for user in leaderboard_data
    ]

    emit('update_leaderboard', leaderboard_list)



# app/socket_handlers.py or inside dashboard.py
from flask_socketio import SocketIO, emit
from flask_login import current_user
from .models import Goal
from datetime import datetime
now = datetime.utcnow()  


socketio = SocketIO(cors_allowed_origins="*")

@socketio.on("get_goals")
def handle_get_goals():
    if not current_user.is_authenticated:
        emit("update_goals", [])
        return

    goals = Goal.query.filter_by(user_id=current_user.id).all()
    goal_data = [{
        "title": g.title,
        "description": g.description,
        "deadline": g.deadline.strftime("%Y-%m-%d") if isinstance(g.deadline, datetime) else g.deadline,
        "status": g.status,
        "priority": g.priority,
        "progress": g.progress,
        "quote": g.quote or "Stay consistent and committed!",
        "tags": [t.strip() for t in g.tags.split(',')] if g.tags else []
    } for g in goals]

    emit("update_goals", goal_data)


@dashboard.route("/set-weekly-goal", methods=["GET", "POST"])
@login_required
def set_weekly_goal():
    if current_user.role != "host":
        flash("Only hosts can set goals.", "danger")
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        deadline = request.form.get("deadline")
        priority = request.form.get("priority")
        tags = request.form.get("tags")
        quote = request.form.get("quote")

        from app.models import User, Goal  # if using relative imports
        volunteers = User.query.filter_by(role="volunteer").all()
        for v in volunteers:
            new_goal = Goal(
                user_id=v.id,
                title=title,
                description=description,
                deadline=datetime.strptime(deadline, "%Y-%m-%d") if deadline else None,
                priority=priority,
                tags=tags,
                quote=quote,
                status="Pending"
            )

            db.session.add(new_goal)
        db.session.commit()

        flash("Weekly goal assigned to all volunteers!", "success")
        return redirect(url_for("dashboard.set_weekly_goal"))

    return render_template("host/set_weekly_goal.html")



# Example check-in logic

from flask_login import current_user

@dashboard.route('/checkin/<int:event_id>', methods=['POST'])
@login_required
def check_in(event_id):
    attendance = AttendanceRecord.query.filter_by(
        volunteer_id=current_user.id,
        event_id=event_id
    ).first()
    if attendance:
        attendance.checked_in = True
        db.session.commit()
        return {"success": True, "message": "Checked in successfully"}
    else:
        return {"success": False, "message": "No booking found for this event"}



from flask import Blueprint, render_template
from flask_login import login_required, current_user
from flask_socketio import emit
from app import socketio, db
from app.models import ImpactEntry



@dashboard.route('/impact-timeline')
@login_required
def impact_timeline_v2():
    return render_template("impact_timeline.html", impact_entries=[])

@socketio.on("submit_review")
def handle_submit_review(data):
    review = VolunteerReview(
        name=data.get("name"),
        text=data.get("text"),
        rating=int(data.get("rating", 5)),
        tags=data.get("tags", "")
    )
    db.session.add(review)
    db.session.commit()
    emit_reviews()

@socketio.on("get_reviews")
def emit_reviews():
    reviews = VolunteerReview.query.order_by(VolunteerReview.timestamp.desc()).all()
    emit("update_reviews", [r.to_dict() for r in reviews])

@dashboard.route('/badges', endpoint='badges')
@login_required
def badges():
    earned = Badge.query.filter(Badge.user_id == current_user.id).all()
    locked = Badge.query.filter(~Badge.id.in_([b.id for b in earned])).all()
    return render_template("view_badges.html", badges={"earned": earned, "locked": locked})


# Inside dashboard.py or a registered Blueprint
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from flask_socketio import emit



@dashboard.route('/send-notification', methods=['POST'])
@login_required
def send_notification():
    data = request.get_json()
    message = data.get('message')
    user_id = current_user.id
    room = f"user_{user_id}"
    socketio.emit('new_notification', {'message': message}, room=room)
    return jsonify({'status': 'sent'})

from flask import abort
from flask_login import login_required, current_user
from app.models import Notification
from app import db
@dashboard.route('/notifications/mark_read/<int:notification_id>', methods=['POST'])
@login_required
def mark_read(notification_id):
    notification = Notification.query.get(notification_id)
    if notification and notification.user_id == current_user.id:
        notification.read = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Unauthorized'}), 403

@dashboard.route('/notifications/delete/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    notification = Notification.query.get(notification_id)
    if notification and notification.user_id == current_user.id:
        db.session.delete(notification)
        db.session.commit()
        return '', 204
    return jsonify({'error': 'Unauthorized'}), 403

import os
from werkzeug.utils import secure_filename
from flask import current_app

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import db, Badge
from app.utils.decorators import roles_required
import os

from app.forms import BadgeForm

@dashboard.route('/host/create-badge', methods=['GET', 'POST'])
@login_required
@roles_required('host')
def create_badge():
    form = BadgeForm()

    if form.validate_on_submit():
        name = form.name.data
        desc = form.description.data
        condition_type = form.condition_type.data
        condition_value = form.condition_value.data

        file = form.image_file.data
        if file and file.filename:
            filename = secure_filename(file.filename)
            upload_path = os.path.join(current_app.root_path, 'static/badges', filename)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)
            file.save(upload_path)
            image_url = f'/static/badges/{filename}'
        else:
            image_url = '/static/badges/default.png'

        badge = Badge(
            name=name,
            description=desc,
            image_url=image_url,
            condition_type=condition_type,
            condition_value=condition_value,
            created_by=current_user.id
        )
        db.session.add(badge)
        db.session.commit()
        flash('Badge created successfully!', 'success')
        return redirect(url_for('dashboard.view_badgess'))

    return render_template('host/create_badge.html', form=form)


@dashboard.route('/host/bulk-badge-upload', methods=['POST'])
@login_required
@roles_required('host')
def bulk_badge_upload():
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(request.referrer or url_for('dashboard.create_badge'))

    import csv
    import io
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    csv_input = csv.DictReader(stream)

    created = 0
    for row in csv_input:
        badge = Badge(
            name=row['name'],
            description=row['description'],
            level=row['level'],
            tags=row['tags'],
            xp_reward=int(row['xp_reward']),
            condition_type=row['condition_type'],
            condition_value=int(row['condition_value']),
            created_by=current_user.id,
        )
        db.session.add(badge)
        created += 1

    db.session.commit()
    flash(f'Successfully uploaded {created} badges from CSV.', 'success')
    return redirect(url_for('dashboard.create_badge'))


@dashboard.route('/volunteer/badges')
@login_required
def view_badgess():
    from app.models import Badge, UserBadge, CheckIn, db, User



    all_badges = Badge.query.all()
    user_badge_ids = [ub.badge_id for ub in UserBadge.query.filter_by(user_id=current_user.id).all()]

    badges = []
    for badge in all_badges:
        is_unlocked = badge.id in user_badge_ids
        progress = 100 if is_unlocked else 0

        if not is_unlocked and badge.condition_type and badge.condition_value:
            if badge.condition_type == 'checkin':
                user_checkins = Checkin.query.filter_by(user_id=current_user.id).count()
                progress = min(int((user_checkins / badge.condition_value) * 100), 100)

            elif badge.condition_type == 'event_attendance':
                from sqlalchemy import and_

                attended_events = CheckIn.query.filter(and_(CheckIn.user_id == current_user.id,CheckIn.checkin_time.isnot(None))).count()



                progress = min(int((attended_events / badge.condition_value) * 100), 100)

            # Auto-unlock badge if progress is complete and not already unlocked
            if progress == 100:
                new_unlock = UserBadge(user_id=current_user.id, badge_id=badge.id)
                db.session.add(new_unlock)
                db.session.commit()
                is_unlocked = True
                user_badge_ids.append(badge.id)  # Update list to reflect

        # Get creator name
        creator_name = "Host"
        if badge.created_by:
            creator = User.query.get(badge.created_by)
            if creator:
                creator_name = creator.name

        # Append badge with all info
        badges.append({
            'id': badge.id,
            'name': badge.name,
            'description': badge.description,
            'image_url': badge.image_url,
            'level': badge.level,
            'xp_reward': badge.xp_reward or 0,
            'condition_type': badge.condition_type,
            'condition_value': badge.condition_value,
            'tags': badge.tags.split(',') if badge.tags else [],
            'unlocked': is_unlocked,
            'progress': progress,
            'set_by': creator_name
        })

    return render_template('volunteer/badges.html', badges=badges)


    


@dashboard.route('/host/delete-badge/<int:badge_id>', methods=['POST'])
@login_required
@roles_required('host')
def delete_badge(badge_id):
    badge = Badge.query.get_or_404(badge_id)

    # Ensure only creator can delete the badge
    if badge.created_by != current_user.id:
        flash("You are not authorized to delete this badge.", "danger")
        return redirect(url_for('dashboard.view_badgess'))

    # Delete badge image file (if not default)
    if badge.image_url and 'default.png' not in badge.image_url:
        image_path = os.path.join(current_app.root_path, badge.image_url.strip('/'))
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as e:
                current_app.logger.warning(f"Error deleting badge image: {e}")

    db.session.delete(badge)
    db.session.commit()
    flash('Badge deleted successfully!', 'success')
    return redirect(url_for('dashboard.view_badgess'))



@dashboard.route('/volunteer/unlock-badge/<int:badge_id>', methods=['POST'])
@login_required
def unlock_badge(badge_id):
    badge = Badge.query.get_or_404(badge_id)
    existing = UserBadge.query.filter_by(user_id=current_user.id, badge_id=badge.id).first()
    
    if existing:
        return jsonify({'status': 'already_unlocked'})

    progress = 0
    if badge.condition_type == 'checkin':
        checkin_count = Checkin.query.filter_by(user_id=current_user.id).count()
        progress = int((checkin_count / badge.condition_value) * 100)
    elif badge.condition_type == 'event_attendance':
        attended = Attendance.query.filter_by(user_id=current_user.id, attended=True).count()
        progress = int((attended / badge.condition_value) * 100)

    if progress >= 100:
        new_badge = UserBadge(user_id=current_user.id, badge_id=badge.id)
        db.session.add(new_badge)
        db.session.commit()
        return jsonify({'status': 'unlocked'})
    
    return jsonify({'status': 'denied', 'message': 'Progress not sufficient to unlock.'})

# View managed volunteers
@dashboard.route('/host/manage-volunteers')
@login_required
@roles_required('host')
def manage_volunteers():
    all_volunteers = User.query.filter_by(role='volunteer').all()
    managed = current_user.managed_volunteers
    return render_template('host/manage_volunteers.html', all_volunteers=all_volunteers, managed=managed)

# Add volunteer
@dashboard.route('/host/add-volunteer/<int:volunteer_id>', methods=['POST'])
@login_required
@roles_required('host')
def add_volunteer(volunteer_id):
    volunteer = User.query.get_or_404(volunteer_id)
    if volunteer not in current_user.managed_volunteers:
        current_user.managed_volunteers.append(volunteer)
        db.session.commit()
    return redirect(url_for('dashboard.manage_volunteers'))

# Remove volunteer
@dashboard.route('/host/remove-volunteer/<int:volunteer_id>', methods=['POST'])
@login_required
@roles_required('host')
def remove_volunteer(volunteer_id):
    volunteer = User.query.get_or_404(volunteer_id)
    if volunteer in current_user.managed_volunteers:
        current_user.managed_volunteers.remove(volunteer)
        db.session.commit()
    return redirect(url_for('dashboard.manage_volunteers'))
@dashboard.route('/host/create-volunteer', methods=['POST'])
@login_required
@roles_required('host')
def create_volunteer_account():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']

    if User.query.filter_by(email=email).first():
        flash("Email already exists.", "danger")
        return redirect(url_for('dashboard.manage_volunteers'))

    new_vol = User(
        name=name,
        email=email,
        password=generate_password_hash(password),  # make sure to import this
        role='volunteer'
    )
    db.session.add(new_vol)
    db.session.commit()
    flash("Volunteer account created successfully!", "success")
    return redirect(url_for('dashboard.manage_volunteers'))


@dashboard.route('/host/delete-volunteer/<int:volunteer_id>', methods=['POST'])
@login_required
@roles_required('host')
def delete_volunteer_account(volunteer_id):
    volunteer = User.query.get_or_404(volunteer_id)
    if volunteer.role != 'volunteer':
        flash("Only volunteers can be deleted this way.", "danger")
        return redirect(url_for('dashboard.manage_volunteers'))

    db.session.delete(volunteer)
    db.session.commit()
    flash("Volunteer account deleted.", "warning")
    return redirect(url_for('dashboard.manage_volunteers'))

@dashboard.route('/assign-volunteer/<int:volunteer_id>', methods=['POST'])
@login_required
@roles_required('host')
def assign_volunteer_to_event(volunteer_id):
    event_id = request.form.get('event_id')
    volunteer = User.query.get_or_404(volunteer_id)
    event = Event.query.get_or_404(event_id)

    if volunteer.role != 'volunteer':
        flash("Only volunteers can be assigned to events.", "warning")
        return redirect(url_for('dashboard.manage_volunteers'))

    if current_user.id != event.host_id:
        flash("You are not authorized to assign to this event.", "danger")
        return redirect(url_for('dashboard.manage_volunteers'))

    # Check if already assigned
    existing = Booking.query.filter_by(user_id=volunteer.id, event_id=event.id).first()
    if existing:
        flash("Volunteer is already assigned to this event.", "info")
    else:
        booking = Booking(user_id=volunteer.id, event_id=event.id)
        db.session.add(booking)
        db.session.commit()
        flash("Volunteer assigned successfully!", "success")

    return redirect(url_for('dashboard.manage_volunteers'))

@dashboard.route('/volunteer/<int:volunteer_id>/reset-password', methods=['POST'])
@login_required
def reset_volunteer_password(volunteer_id):
    volunteer = User.query.get_or_404(volunteer_id)

    # Only hosts can reset volunteers they manage
    if volunteer.role != 'volunteer':
        flash('Invalid user type.', 'danger')
        return redirect(url_for('dashboard.manage_volunteers'))

    # Reset to a default password or generate one
    new_password = 'volunteer123'  # Or use random string
    volunteer.password = generate_password_hash(new_password)
    db.session.commit()

    flash(f"Password reset for {volunteer.name}. New password: {new_password}", 'info')
    return redirect(url_for('dashboard.manage_volunteers'))

@dashboard.route('/volunteer/<int:volunteer_id>/toggle-status', methods=['POST'])
@login_required
def toggle_volunteer_status(volunteer_id):
    volunteer = User.query.get_or_404(volunteer_id)

    if volunteer.role != 'volunteer':
        flash('Invalid user type.', 'danger')
        return redirect(url_for('dashboard.manage_volunteers'))

    # Toggle status (example: assume 'is_active' boolean field)
    volunteer.is_volunteer_active = not volunteer.is_volunteer_active  # ✅

    db.session.commit()

    status = 'activated' if volunteer.is_active else 'deactivated'
    flash(f"{volunteer.name} has been {status}.", 'success')
    return redirect(url_for('dashboard.manage_volunteers'))

@dashboard.route('/dashboard/bulk-upload', methods=['POST'])
@login_required
@roles_required('host')
def bulk_upload_volunteers():
    from app import db
    from app.models import User
    import csv
    import io
    from werkzeug.security import generate_password_hash

    file = request.files.get('csv_file')

    if not file or not file.filename.endswith('.csv'):
        flash("Please upload a valid CSV file.", "danger")
        return redirect(url_for('dashboard.manage_volunteers'))

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    created = 0
    skipped = 0

    for row in reader:
        name = row.get('name', '').strip()
        email = row.get('email', '').strip()
        password = row.get('password', 'defaultpass123').strip()
        gender = row.get('gender', '').strip().capitalize()  # Capitalize: 'male' → 'Male'

        if not name or not email:
            skipped += 1
            continue

        if User.query.filter_by(email=email).first():
            skipped += 1
            continue

        try:
            user = User(
                name=name,
                email=email,
                role='volunteer',
                password=generate_password_hash(password),
                gender=gender if gender in ['Male', 'Female', 'Other'] else 'Other',
                is_volunteer_active=True
            )
            db.session.add(user)
            created += 1
        except Exception as e:
            db.session.rollback()
            skipped += 1
            print(f"Failed to add {email}: {e}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash("Database commit failed.", "danger")
        print(f"Commit error: {e}")
        return redirect(url_for('dashboard.manage_volunteers'))

    flash(f"{created} volunteers created, {skipped} skipped.", "success")
    return redirect(url_for('dashboard.manage_volunteers'))




@dashboard.route('/api/volunteer-activity-calendar')
@login_required
@roles_required('host')
def volunteer_activity_calendar():
    from collections import defaultdict
    import datetime

    data = defaultdict(int)
    participations = db.session.query(Participation.date)\
        .filter(Participation.date >= datetime.date.today() - datetime.timedelta(days=120))\
        .all()

    for (date,) in participations:
        data[date.isoformat()] += 1

    result = [{"date": date, "count": count} for date, count in data.items()]
    return jsonify(result)



@dashboard.route('/volunteer-analytics')
@login_required
def view_volunteer_analytics():  # <- Renamed to avoid duplicate function names
    from .models import User, Event, AttendanceRecord
    from sqlalchemy import func
    from flask_login import current_user

    # Top 5 volunteers by XP
    top_volunteers = User.query.filter_by(role='volunteer').order_by(User.xp.desc()).limit(5).all()
    top_volunteers_data = [(v.name, v.xp) for v in top_volunteers]

    # Total volunteers and total XP
    total_volunteers = User.query.filter_by(role='volunteer').count()
    total_xp = db.session.query(func.coalesce(func.sum(User.xp), 0)).scalar()

    # Monthly participation chart
    monthly_data = (
        db.session.query(func.strftime('%Y-%m', AttendanceRecord.timestamp), func.count())
        .join(User, User.id == AttendanceRecord.volunteer_id)
        .filter(User.role == 'volunteer')
        .group_by(func.strftime('%Y-%m', AttendanceRecord.timestamp))
        .order_by(func.strftime('%Y-%m', AttendanceRecord.timestamp))
        .all()
    )
    months = [row[0] for row in monthly_data]
    counts = [row[1] for row in monthly_data]

    # Event category breakdown
    category_data = (
        db.session.query(Event.category, func.count(Event.id))
        .group_by(Event.category)
        .all()
    )
    category_labels = [row[0] if row[0] else "Uncategorized" for row in category_data]
    category_counts = [row[1] for row in category_data]

    # XP/Level progress for current user
    xp = getattr(current_user, 'xp', 0)
    level = (xp // 100) or 1
    next_level = ((xp // 100) + 1) * 100
    xp_progress = xp % 100
    percent_to_next = round((xp_progress / 100) * 100, 1)

    return render_template('volunteer_analytics.html',
                           user=current_user,
                           top_volunteers=top_volunteers_data,
                           total_volunteers=total_volunteers,
                           total_xp=total_xp,
                           months=months,
                           counts=counts,
                           categories=category_labels,
                           category_counts=category_counts,
                           xp=xp,
                           next_level=next_level,
                           xp_progress=xp_progress,
                           percent_to_next=percent_to_next)
@dashboard.route('/analytics/volunteers')
@login_required
@roles_required('host')
def volunteer_analytics():
    from datetime import datetime
    from sqlalchemy import or_, func
    from app.models import User, Event, Reward, AttendanceRecord, Booking
    from app import db

    now = datetime.utcnow()

    # Total volunteers
    volunteers = User.query.filter_by(role='volunteer').all()
    total_volunteers = len(volunteers)

    # Total bookings
    total_bookings = Booking.query.count()

    # Total events
    total_events = Event.query.count()

    # Top volunteers by total hours
    top_volunteers = sorted(
        volunteers, key=lambda v: v.total_hours or 0, reverse=True
    )[:10]

    # Live volunteers = checked-in volunteers with no check_out_time
    live_volunteer_count = (
        db.session.query(AttendanceRecord)
        .join(User, AttendanceRecord.volunteer_id == User.id)
        .filter(
            AttendanceRecord.status == 'present',
            AttendanceRecord.check_out_time == None,
            User.role == 'volunteer'
        )
        .count()
    )

    # Ongoing events = start_time <= now AND end_time >= now
    ongoing_events = Event.query.filter(
        or_(Event.start_time == None, Event.start_time <= now),
        or_(Event.end_time == None, Event.end_time >= now)
    ).all()
    ongoing_events_count = len(ongoing_events)

    # Total and average volunteer hours
    total_hours = sum(v.total_hours or 0 for v in volunteers)
    avg_hours = round(total_hours / total_volunteers, 2) if total_volunteers else 0.0

    # Total XP
    total_xp = sum(v.xp or 0 for v in volunteers)

    # Gender ratio
    male_count = User.query.filter_by(role='volunteer', gender='Male').count()
    female_count = User.query.filter_by(role='volunteer', gender='Female').count()
    other_count = User.query.filter(User.role == 'volunteer', User.gender.notin_(['Male', 'Female'])).count()

    gender_ratio = {
        'male': male_count,
        'female': female_count,
        'other': other_count
    }

    # XP chart (range)
    xp_labels = ['0-100 XP', '101-250 XP', '251-500 XP', '501+ XP']
    xp_values = [
        len([v for v in volunteers if (v.xp or 0) <= 100]),
        len([v for v in volunteers if 100 < (v.xp or 0) <= 250]),
        len([v for v in volunteers if 250 < (v.xp or 0) <= 500]),
        len([v for v in volunteers if (v.xp or 0) > 500]),
    ]

    # Heatmap data: attendance per date
    heatmap_raw = (
        db.session.query(
            func.date(AttendanceRecord.check_in_time).label("date"),
            func.count().label("count")
        )
        .filter(AttendanceRecord.status == 'present')
        .group_by(func.date(AttendanceRecord.check_in_time))
        .all()
    )
    heatmap_data = [{'date': str(r.date), 'count': r.count} for r in heatmap_raw]

    return render_template(
        'analytics_volunteers.html',
        top_volunteers=top_volunteers,
        live_volunteer_count=live_volunteer_count,
        ongoing_events_count=ongoing_events_count,
        total_xp=total_xp,
        avg_hours=avg_hours,
        total_volunteers=total_volunteers,
        total_bookings=total_bookings,
        total_events=total_events,
        gender_ratio=gender_ratio,
        xp=current_user.xp or 0,
        next_level=1000,
        percent_to_next=(current_user.xp or 0) / 1000 * 100,
        rewards=Reward.query.all(),
        xp_labels=xp_labels,
        xp_values=xp_values,
        heatmap_data=heatmap_data
    )




# routes.py or dashboard.py

@dashboard.route('/event/<int:event_id>/checkout/<int:volunteer_id>', methods=['POST'])
@login_required
@roles_required('host')
def check_out(event_id, volunteer_id):
    from datetime import datetime

    record = AttendanceRecord.query.filter_by(
        event_id=event_id, volunteer_id=volunteer_id
    ).first_or_404()

    if record.check_out_time:
        flash("Volunteer already checked out.", "warning")
        return redirect(url_for('dashboard.view_event_attendance', event_id=event_id))

    record.check_out_time = datetime.utcnow()
    duration = (record.check_out_time - record.check_in_time).total_seconds() / 3600.0

    # ✅ Update total hours
    volunteer = User.query.get(volunteer_id)
    if volunteer:
        volunteer.total_hours = (volunteer.total_hours or 0) + duration

    db.session.commit()

    flash("Volunteer checked out successfully.", "success")
    return redirect(url_for('dashboard.view_event_attendance', event_id=event_id))
@dashboard.route('/checkin/manual/<int:booking_id>', methods=['POST'])
@login_required
@roles_required('host')
def manual_checkin(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.checked_in:
        flash(f"{booking.user.name} is already checked in.", "info")
        return redirect(request.referrer or url_for('dashboard.manage_events'))
    
    # Mark booking as checked in and record check-in time
    booking.checked_in = True
    booking.check_in_time = datetime.utcnow()

    # Create or update AttendanceRecord
    attendance = AttendanceRecord.query.filter_by(event_id=booking.event_id, volunteer_id=booking.user_id).first()
    if not attendance:
        attendance = AttendanceRecord(
            event_id=booking.event_id,
            volunteer_id=booking.user_id,
            checked_in=True,
            timestamp=datetime.utcnow(),
            status='present'
        )
        db.session.add(attendance)
    else:
        attendance.checked_in = True
        attendance.timestamp = datetime.utcnow()
        attendance.status = 'present'

    db.session.commit()
    flash(f"{booking.user.name} has been marked as checked in successfully!", "success")
    return redirect(request.referrer or url_for('dashboard.manage_events'))
