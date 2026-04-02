from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from .models import Event, UserBadge, Booking, Badge, User, AttendanceRecord, Notification
from app import db, socketio
from geopy.distance import geodesic

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
from .socketio_events import emit_full_user_update

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
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)

    all_events = Event.query.filter_by(archived=False).all()
    current_app.logger.info(f"Loaded {len(all_events)} active events")

    event_data = []

    # 📍 User location
    try:
        user_loc = (float(current_user.latitude), float(current_user.longitude))
    except Exception as e:
        current_app.logger.warning(f"User location not available: {e}")
        user_loc = None

    # 🔄 Loop events
    for event in all_events:
        include_event = True

        if user_loc and event.latitude and event.longitude:
            try:
                distance_km = geodesic((event.latitude, event.longitude), user_loc).km
                include_event = distance_km <= 20
            except Exception as e:
                current_app.logger.warning(f"Distance error: {e}")
                include_event = False

        if include_event:
            booking = Booking.query.filter_by(
                event_id=event.id,
                user_id=current_user.id
            ).first()

            attendance = AttendanceRecord.query.filter_by(
                event_id=event.id,
                volunteer_id=current_user.id
            ).first()

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

            event_data.append({
                "event": event,
                "status": status
            })

    # 🔥 ===== FIX START (VERY IMPORTANT) =====

    from sqlalchemy import func
    from app.models import Goal

    volunteers = User.query.filter_by(role='volunteer').count()
    events_count = Event.query.filter_by(archived=False).count()
    cities = db.session.query(func.count(func.distinct(Event.location))).scalar()
    
    # 🔥 ===== NEW: Goals & Popular Places =====
    # 1. Fetch Goals for the current user
    user_goals = Goal.query.filter_by(user_id=current_user.id).limit(3).all()
    
    # 2. Calculate popular nearby places based on the filtered nearby events
    places_counter = {}
    for data in event_data:
        loc = data["event"].location
        if not loc:
            continue
        # Weight popularity by existing bookings + a base of 1
        bookings_count = len(data["event"].bookings)
        places_counter[loc] = places_counter.get(loc, 0) + bookings_count + 5  # added 5 as baseline interest
        
    # Sort places by popularity (highest first) and take top 4
    sorted_places = sorted(places_counter.items(), key=lambda x: x[1], reverse=True)[:4]
    
    popular_places = []
    for loc_name, interest in sorted_places:
        popular_places.append({
            "name": loc_name,
            "interest": interest
        })

    # 🔥 ===== FIX END =====

    return render_template(
        'dashboard.html',
        user=current_user,
        events=event_data,          # ⚠️ for event cards
        volunteers=volunteers,     # ✅ stats
        events_count=events_count, # ✅ stats
        cities=cities,             # ✅ stats
        user_goals=user_goals,     # ✅ dynamic goals
        popular_places=popular_places, # ✅ dynamic places
        current_time=now,
        timedelta=timedelta
    )

@dashboard.route('/api/nearby_pois')
@login_required
def get_nearby_pois():
    """Fetches real points of interest (Parks, Malls, Malls, Temples) using Overpass API."""
    import requests
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    if not lat or not lon:
        return jsonify({'success': False, 'message': 'Location missing'}), 400

    # Overpass QL query to find parks, shops (malls), temples, attractions, etc.
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["leisure"~"park|nature_reserve|playground|sports_centre"](around:15000,{lat},{lon});
      node["shop"~"mall|supermarket|department_store"](around:15000,{lat},{lon});
      node["amenity"~"place_of_worship|museum|cinema|stadium|theatre"](around:15000,{lat},{lon});
      node["tourism"~"attraction|viewpoint|museum|theme_park"](around:15000,{lat},{lon});
    );
    out 12;
    """
    
    try:
        # We use 'nwr' to match nodes, ways, and relations — many parks/malls are ways
        # Simplified query to reduce server load
        query = f"""
        [out:json][timeout:25];
        (
          nwr["leisure"="park"](around:10000,{lat},{lon});
          nwr["shop"="mall"](around:10000,{lat},{lon});
          nwr["amenity"="place_of_worship"](around:10000,{lat},{lon});
          nwr["tourism"="attraction"](around:10000,{lat},{lon});
        );
        out center 12;
        """
        
        headers = {'User-Agent': 'ReEarth-EcoApp/1.0'}
        response = requests.get(overpass_url, params={'data': query}, timeout=20, headers=headers)
        
        if response.status_code != 200:
            print(f"Overpass Server Error ({response.status_code}). Content: {response.text[:100]}")
            return jsonify({'success': False, 'message': 'The map service is currently busy. Please try again in 10 seconds.'})

        data = response.json()
        elements = data.get('elements', [])
        
        results = []
        for el in elements:
            tags = el.get('tags', {})
            name = tags.get('name')
            if not name: continue  # Skip unnamed places
            
            # Identify the primary category detected
            category = tags.get('leisure') or tags.get('shop') or tags.get('amenity') or tags.get('tourism')
            
            # Map category to a friendly name and image keyword
            cat_map = {
                'park': ('Nature Park', 'park,greenery'),
                'nature_reserve': ('Nature Reserve', 'forest,nature'),
                'playground': ('Public Space', 'park'),
                'sports_centre': ('Activity Center', 'sports'),
                'mall': ('Shopping Hub', 'mall,building'),
                'supermarket': ('Shopping Hub', 'supermarket'),
                'department_store': ('Shopping Hub', 'shopping'),
                'place_of_worship': ('Spiritual Center', 'temple,shrine'),
                'museum': ('Museum', 'museum'),
                'cinema': ('Cinema', 'cinema'),
                'stadium': ('Stadium', 'stadium'),
                'theatre': ('Theater', 'theater'),
                'attraction': ('Tourist Spot', 'monument'),
                'viewpoint': ('Viewpoint', 'landscape'),
                'theme_park': ('Adventure Park', 'funfair')
            }
            cat_name, keyword = cat_map.get(category, ('Popular Hub', 'city,building'))
            
            # Realistic image keywords for LoremFlickr
            img_url = f"https://loremflickr.com/600/400/{keyword}?{name.replace(' ', '')}"
            
            results.append({
                'name': name,
                'category': cat_name,
                'interest': 100 + (el.get('id', 0) % 250), # Simulated growing interest
                'image': img_url
            })
            
        return jsonify({'success': True, 'places': results})
    except Exception as e:
        print(f"Error fetching POIs: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@dashboard.route('/dashboard1')
@login_required
def dashboard1_home():
    archive_expired_events()
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)

    all_events = Event.query.filter_by(archived=False).all()
    current_app.logger.info(f"[Dashboard1] Loaded {len(all_events)} active events")

    event_data = []

    # 📍 User location
    try:
        user_loc = (float(current_user.latitude), float(current_user.longitude))
    except Exception as e:
        current_app.logger.warning(f"[Dashboard1] Location error: {e}")
        user_loc = None

    # 🔄 Loop events
    for event in all_events:
        include_event = True

        if user_loc and event.latitude and event.longitude:
            try:
                distance_km = geodesic((event.latitude, event.longitude), user_loc).km
                include_event = distance_km <= 20
            except Exception as e:
                current_app.logger.warning(f"[Dashboard1] Distance error: {e}")
                include_event = False

        if include_event:
            booking = Booking.query.filter_by(
                event_id=event.id,
                user_id=current_user.id
            ).first()

            attendance = AttendanceRecord.query.filter_by(
                event_id=event.id,
                volunteer_id=current_user.id
            ).first()

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

            event_data.append({
                "event": event,
                "status": status
            })

    # 📊 STATS
    from sqlalchemy import func

    volunteers = User.query.filter_by(role='volunteer').count()
    events_count = Event.query.filter_by(archived=False).count()
    cities = db.session.query(func.count(func.distinct(Event.location))).scalar()

    # 🔥 RETURN dashboard1.html
    return render_template(
        'dashboard1.html',
        user=current_user,
        events=event_data,
        volunteers=volunteers,
        events_count=events_count,
        cities=cities,
        current_time=now,
        timedelta=timedelta
    )
    
# Update goal progress route
@dashboard.route('/update_goal_progress/<int:goal_id>', methods=['POST'])
@login_required
def update_goal_progress(goal_id):
    from app.models import Goal, XPLog
    goal = Goal.query.get(goal_id)
    if not goal or goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Goal not found or unauthorized.'}), 403
        
    data = request.get_json()
    new_progress = int(data.get('progress', 0))
    if new_progress > 100:
        new_progress = 100
        
    goal.progress = new_progress
    if new_progress >= 100 and goal.status != 'Completed':
        goal.status = 'Completed'
        # Award xp
        xp_reward = goal.xp_reward if goal.xp_reward else 50
        current_user.xp = (current_user.xp or 0) + xp_reward
        log = XPLog(user_id=current_user.id, xp=xp_reward, reason=f'Completed Goal: {goal.title}')
        db.session.add(log)
        
    db.session.commit()
    return jsonify({'success': True, 'progress': goal.progress, 'status': goal.status})

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
    
    emit_full_user_update(current_user)
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

# ============================================================
#  FIXED profile() ROUTE — replace in dashboard.py
# ============================================================

@dashboard.route("/profile")
@login_required
def profile():
    from collections import defaultdict
    from app.models import User, UserBadge, XPLog, AttendanceRecord, Badge

    user_id = current_user.id
    user = User.query.get(user_id)

    # ── 1. Earned badges (UserBadge → Badge join) ──────────
    user_badge_rows = UserBadge.query.filter_by(user_id=user_id).all()

    earned_badges = []
    for ub in user_badge_rows:
        badge = Badge.query.get(ub.badge_id)
        if badge:
            earned_badges.append({
                'id':          badge.id,
                'name':        badge.name,
                'description': badge.description or '',
                'icon_url':    badge.image_url or '/static/badges/default.png',
                'rarity':      badge.level or 'Common',
                'xp':          badge.xp_reward or 0,
                'earned_date': ub.awarded_at
            })

    # ── 2. XP Progress ─────────────────────────────────────
    current_xp    = user.xp or 0
    current_level = user.level or 1
    xp_for_next   = (current_level + 1) * 100
    progress_pct  = min(100, int((current_xp / xp_for_next) * 100))
    progress = {
        "current_xp":        current_xp,
        "current_level":     current_level,
        "xp_for_next_level": xp_for_next,
        "progress_percent":  progress_pct
    }

    # ── 3. XP chart data (cumulative) ──────────────────────
    xp_logs = XPLog.query.filter_by(user_id=user_id)\
                         .order_by(XPLog.timestamp.asc()).all()

    xp_labels = [log.timestamp.strftime("%d %b") for log in xp_logs]
    xp_data   = [log.xp for log in xp_logs]  # per-log XP

    # ── 4. Monthly XP ──────────────────────────────────────
    monthly_xp = defaultdict(int)
    for log in xp_logs:
        monthly_xp[log.timestamp.strftime("%b %Y")] += log.xp
    monthly_xp_labels = list(monthly_xp.keys())
    monthly_xp_data   = list(monthly_xp.values())

    # ── 5. Volunteer hours (per date) ──────────────────────
    attendance_records = AttendanceRecord.query.filter_by(
        volunteer_id=user_id
    ).all()

    hours_by_date = defaultdict(float)
    for rec in attendance_records:
        if rec.timestamp:
            d = rec.timestamp.strftime("%d %b")
            hours_by_date[d] += rec.calculated_hours or 0

    volunteer_hours_labels = list(hours_by_date.keys())
    volunteer_hours_values = list(hours_by_date.values())

    # ── 6. Event participation (category breakdown) ────────
    from app.models import Event, Booking
    from collections import Counter
    bookings = Booking.query.filter_by(user_id=user_id).all()
    category_counter = Counter()
    for b in bookings:
        ev = Event.query.get(b.event_id)
        if ev:
            category_counter[ev.category or "General"] += 1

    event_participation_labels = list(category_counter.keys())
    event_participation_data   = list(category_counter.values())

    # ── 7. Badge chart ─────────────────────────────────────
    badge_labels = [b['name'] for b in earned_badges]
    badge_data   = [b['xp'] for b in earned_badges]

    # ── 8. Impact stats ────────────────────────────────────
    total_events       = len(attendance_records)
    total_hours_val    = sum(rec.calculated_hours or 0 for rec in attendance_records)
    total_badges_count = len(earned_badges)

    from app.models import Booking as BookingModel
    # Count certificates = completed tasks
    total_certs = AttendanceRecord.query.filter_by(
        volunteer_id=user_id, task_completed=True
    ).count()

    # ── 9. Total achievements ──────────────────────────────
    total_achievements = total_badges_count + total_events + total_certs

    # ── 10. Activities (recent XP log — human readable) ────
    recent_logs = XPLog.query.filter_by(user_id=user_id)\
                             .order_by(XPLog.timestamp.desc())\
                             .limit(10).all()
    activities = []
    for log in recent_logs:
        label = log.reason or f"Earned {log.xp} XP"
        activities.append(f"{label} (+{log.xp} XP) — {log.timestamp.strftime('%d %b %Y')}")

    # ── 11. Pass impact_stats dict for template ────────────
    impact_stats = {
        'total_events':       total_events,
        'total_hours':        round(total_hours_val, 1),
        'total_badges':       total_badges_count,
        'total_certificates': total_certs
    }

    return render_template(
        "profile.html",
        user                      = current_user,
        earned_badges             = earned_badges,
        progress                  = progress,
        xp_labels                 = xp_labels,
        xp_data                   = xp_data,
        monthly_xp_labels         = monthly_xp_labels,
        monthly_xp_data           = monthly_xp_data,
        volunteer_hours_labels    = volunteer_hours_labels,
        volunteer_hours_data      = volunteer_hours_values,   # ← list, not dict
        event_participation_labels= event_participation_labels,
        event_participation_data  = event_participation_data,
        badge_labels              = badge_labels,
        badge_data                = badge_data,
        activities                = activities,
        total_achievements        = total_achievements,
        impact_stats              = impact_stats,
    )

# ─────────────────────────────────────────────
# REPLACE your existing xp_progress_view route
# in app/dashboard.py with this:
# ─────────────────────────────────────────────

from collections import defaultdict

@dashboard.route('/xp-progress')
@login_required
def xp_progress_view():
    from datetime import datetime, timedelta
    from collections import defaultdict

    user = current_user

    # ── XP level math ─────────────────────────────────────────────
    current_xp    = user.xp or 0
    current_level = user.level or 1
    xp_for_next   = (current_level + 1) * 100   # e.g. Level 4 needs 500 XP
    xp_remaining  = max(0, xp_for_next - current_xp)
    next_level    = current_level + 1
    xp_percent    = min(100, round((current_xp / xp_for_next) * 100)) if xp_for_next else 0

    # ── XP logs ───────────────────────────────────────────────────
    xp_logs = XPLog.query.filter_by(user_id=user.id).order_by(XPLog.timestamp.asc()).all()

    # ── Cumulative daily XP (for main line chart, last 30 entries) ─
    cumulative, running = [], 0
    daily_labels = []
    for log in xp_logs[-30:]:
        running += log.xp
        cumulative.append(running)
        daily_labels.append(log.timestamp.strftime('%d %b'))
    # Ensure the last point reflects real current XP
    if cumulative:
        cumulative[-1] = current_xp
    else:
        cumulative   = [current_xp]
        daily_labels = ['Now']

    # ── Monthly XP sums (for mini bar chart) ──────────────────────
    monthly_xp = defaultdict(int)
    for log in xp_logs:
        key = log.timestamp.strftime('%b')
        monthly_xp[key] += log.xp
    # Last 6 months, ensuring order
    today = datetime.utcnow()
    monthly_labels, monthly_data = [], []
    for i in range(5, -1, -1):
        dt  = (today.replace(day=1) - timedelta(days=i * 28))
        key = dt.strftime('%b')
        monthly_labels.append(key)
        monthly_data.append(monthly_xp.get(key, 0))

    # ── Milestones ────────────────────────────────────────────────
    milestones, seen = [], 0
    for log in xp_logs:
        seen += log.xp
        if log.reason:
            milestones.append({
                'title': log.reason,
                'date':  log.timestamp.strftime('%d %b %Y'),
                'xp':    log.xp
            })
    milestones = milestones[-10:]

    # ── Earned badges ─────────────────────────────────────────────
    earned_badges = (db.session.query(UserBadge, Badge)
                     .join(Badge)
                     .filter(UserBadge.user_id == user.id)
                     .all())

    return render_template(
        'xp_progress.html',
        # XP stats
        current_xp        = current_xp,
        current_level     = current_level,
        next_level        = next_level,
        xp_remaining      = xp_remaining,
        xp_percent        = xp_percent,
        xp_for_next_level = xp_for_next,
        # Chart data
        xp_labels         = daily_labels,
        xp_history        = cumulative,
        monthly_xp_labels = monthly_labels,
        monthly_xp_data   = monthly_data,
        # Supporting data
        milestones        = milestones,
        earned_badges     = earned_badges,
        streak_days       = 0,          # extend later with real streak logic
    )

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
    from datetime import datetime, timedelta
    from collections import defaultdict

    volunteer = User.query.get_or_404(user_id)
    events_attended = (AttendanceRecord.query
                       .filter_by(volunteer_id=user_id)
                       .join(Event)
                       .order_by(AttendanceRecord.timestamp.desc())
                       .all())
    earned_badges = (db.session.query(UserBadge, Badge)
                     .join(Badge)
                     .filter(UserBadge.user_id == user_id)
                     .all())

    # ── Build monthly XP chart (last 6 months) ──────────────────────
    today = datetime.utcnow()
    monthly_xp = defaultdict(int)
    for record in events_attended:
        if record.timestamp and record.timestamp >= today - timedelta(days=180):
            key = record.timestamp.strftime('%b %Y')
            monthly_xp[key] += record.xp or 0

    # Fill in any missing months so the chart always has 6 points
    labels, data = [], []
    for i in range(5, -1, -1):
        month_dt = today.replace(day=1) - timedelta(days=i * 28)
        key = month_dt.strftime('%b %Y')
        labels.append(month_dt.strftime('%b'))
        data.append(monthly_xp.get(key, 0))

    return render_template('volunteer_profile.html',
                           volunteer=volunteer,
                           events_attended=events_attended,
                           earned_badges=earned_badges,
                           xp_chart_labels=labels,
                           xp_chart_data=data)









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



from datetime import datetime, date

# ─────────────────────────────────────────────────────────────
# REPLACE your existing @dashboard.route('/calendar') in dashboard.py
# ─────────────────────────────────────────────────────────────

import json
from datetime import date, datetime

@dashboard.route('/calendar')
@login_required
def calendar():
    from app.models import Event, Booking, AttendanceRecord
    today = date.today()
    now_month = today.month
    now_year  = today.year

    COLORS = ['#16a34a','#3b82f6','#f59e0b','#7c3aed','#ef4444','#10b981']

    # ── All events (non-archived) ──────────────────────────────
    all_events = Event.query.filter_by(archived=False).order_by(Event.date.asc()).all()

    # ── Current user's bookings (set of event IDs) ─────────────
    booked_ids = {
        b.event_id
        for b in Booking.query.filter_by(user_id=current_user.id).all()
    }

    # ── Count stats ────────────────────────────────────────────
    upcoming_count   = 0
    booked_count     = len(booked_ids)
    this_month_count = 0
    attended_count   = AttendanceRecord.query.filter_by(
        volunteer_id=current_user.id
    ).count()

    # ── Build serialisable list for the template ───────────────
    events_data = []
    for i, event in enumerate(all_events):
        # Normalise event.date to a plain date object
        if isinstance(event.date, datetime):
            edate = event.date.date()
            time_str = event.date.strftime('%H:%M')
        elif isinstance(event.date, date):
            edate = event.date
            time_str = '00:00'
        else:
            continue  # skip malformed rows

        # Determine status
        if edate < today:
            status = 'completed'
        elif edate == today:
            status = 'ongoing'
            upcoming_count += 1
        else:
            status = 'upcoming'
            upcoming_count += 1

        # This-month count
        if edate.month == now_month and edate.year == now_year:
            this_month_count += 1

        events_data.append({
            'id':          event.id,
            'title':       event.title or 'Untitled',
            'start':       edate.strftime('%Y-%m-%d'),
            'startTime':   time_str,
            'location':    event.location or '—',
            'bookings':    len(event.bookings) if event.bookings else 0,
            'xp':          event.xp_score or 0,
            'description': event.description or 'No description available.',
            'status':      status,
            'category':    event.category or 'General',
            'color':       COLORS[i % len(COLORS)],
            'isBooked':    event.id in booked_ids,
        })

    return render_template(
        'event_calendar.html',
        # ── JSON blob consumed directly by JS ──────────────────
        all_events_json  = json.dumps(events_data),
        # ── Stat tile variables ────────────────────────────────
        upcoming_count   = upcoming_count,
        attended_count   = attended_count,
        booked_count     = booked_count,
        this_month_count = this_month_count,
        today            = today,   # kept for any Jinja use
    )

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
    from app.models import AttendanceRecord, Booking, Event, User

    # Only completed tasks
    records = AttendanceRecord.query.filter_by(task_completed=True).all()

    participants = []

    for record in records:
        user = User.query.get(record.volunteer_id)
        event = Event.query.get(record.event_id)

        # get booking (for xp + date)
        booking = Booking.query.filter_by(
            user_id=record.volunteer_id,
            event_id=record.event_id
        ).first()

        participants.append({
            "name": user.name if user else "Unknown",
            "volunteer_id": record.volunteer_id,
            "event": event.title if event else "Unknown",
            "event_id": record.event_id,  # ✅ FIXED
            "hours": record.calculated_hours or 0,
            "xp_earned": booking.xp_earned if booking else 0,  # ✅ FIXED
            "issued_date": booking.completed_time.strftime('%d %B %Y') if booking and booking.completed_time else "N/A"
        })

    events = Event.query.all()

    return render_template(
        'generate_certificates.html',
        participants=participants,
        events=events
    )
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

# ─────────────────────────────────────────────────────────────
# REPLACE your existing /realtime-attendance route in dashboard.py
# This properly returns volunteers with their real check-in status
# ─────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
# PASTE THIS into dashboard.py — replaces ALL existing /realtime-attendance
# AND /checkin/<int:...> routes
# ═══════════════════════════════════════════════════════════════════

from flask import jsonify, request
from flask_login import login_required, current_user
from datetime import datetime
from app import db, socketio
from app.models import User, Event, Booking, AttendanceRecord


# ─── 1. REALTIME ATTENDANCE — fixed for ALL roles ───────────────────

@dashboard.route('/realtime-attendance')
@login_required
def realtime_attendance():
    """
    Returns volunteer check-in status for the check-in panel.

    HOST   → all volunteers who booked any of this host's events
    ADMIN  → all volunteers across all events
    VOLUNTEER → only their own records
    """
    results = []

    if current_user.role in ('host', 'admin'):

        # ── Get all events created by this host (or ALL events for admin) ──
        if current_user.role == 'admin':
            host_events = Event.query.filter_by(archived=False).all()
        else:
            host_events = Event.query.filter_by(
                creator_id=current_user.id,
                archived=False
            ).all()

        host_event_ids = [e.id for e in host_events]

        # ── Also check ARCHIVED events (volunteers already checked in) ──
        if current_user.role == 'admin':
            all_host_event_ids = [e.id for e in Event.query.all()]
        else:
            all_host_event_ids = [
                e.id for e in Event.query.filter_by(creator_id=current_user.id).all()
            ]

        if not all_host_event_ids:
            return jsonify([])

        # ── Get ALL bookings for this host's events ──
        bookings = Booking.query.filter(
            Booking.event_id.in_(all_host_event_ids)
        ).all()

        # ── Also get AttendanceRecords directly (check-ins may exist without bookings) ──
        attendance_records = AttendanceRecord.query.filter(
            AttendanceRecord.event_id.in_(all_host_event_ids)
        ).all()

        # ── Build a map: volunteer_id → {event_id, attendance, booking} ──
        # We use a dict so each volunteer appears ONCE (most recent event)
        volunteer_map = {}

        # First pass: add from bookings
        for booking in bookings:
            vol_id = booking.user_id
            ev_id  = booking.event_id

            if vol_id not in volunteer_map:
                volunteer_map[vol_id] = {
                    'event_id':    ev_id,
                    'booking':     booking,
                    'attendance':  None,
                }
            else:
                # Keep the more recent booking
                existing_ev = volunteer_map[vol_id]['event_id']
                existing_event = Event.query.get(existing_ev)
                current_event  = Event.query.get(ev_id)
                if existing_event and current_event:
                    if (current_event.date or datetime.min) > (existing_event.date or datetime.min):
                        volunteer_map[vol_id]['event_id'] = ev_id
                        volunteer_map[vol_id]['booking']  = booking

        # Second pass: add attendance records (even if no booking exists)
        for rec in attendance_records:
            vol_id = rec.volunteer_id
            ev_id  = rec.event_id

            if vol_id not in volunteer_map:
                volunteer_map[vol_id] = {
                    'event_id':   ev_id,
                    'booking':    None,
                    'attendance': rec,
                }
            else:
                volunteer_map[vol_id]['attendance'] = rec

        # ── Build result list ──
        for vol_id, info in volunteer_map.items():
            volunteer = User.query.get(vol_id)
            if not volunteer or volunteer.role not in ('volunteer', 'user'):
                continue

            attendance = info['attendance']
            booking    = info['booking']
            event      = Event.query.get(info['event_id'])

            # Determine check-in status
            checked_in   = False
            checkin_time = None
            missed       = False

            if attendance and attendance.status == 'present':
                checked_in   = True
                checkin_time = None
                if attendance.timestamp:
                    checkin_time = attendance.timestamp.strftime('%I:%M %p')

            elif attendance and attendance.checked_in:
                checked_in   = True
                checkin_time = None
                if attendance.timestamp:
                    checkin_time = attendance.timestamp.strftime('%I:%M %p')

            else:
                # Check if event time has passed (missed window)
                if event and event.date:
                    ev_dt = event.date if isinstance(event.date, datetime) else datetime.combine(event.date, datetime.min.time())
                    diff  = (datetime.utcnow() - ev_dt).total_seconds()
                    missed = diff > 1800  # 30 min past event start = missed

            if checked_in:
                status = 'checked_in'
            elif missed:
                status = 'missed'
            else:
                status = 'pending'

            results.append({
                'id':           volunteer.id,
                'name':         volunteer.name or 'Unknown',
                'email':        volunteer.email or '',
                'avatar':       volunteer.profile_pic or '',
                'xp':           volunteer.xp or 0,
                'level':        volunteer.level or 1,
                'checked_in':   checked_in,
                'checkin_time': checkin_time,
                'missed':       missed,
                'status':       status,
                'event_id':     info['event_id'],
                'event_title':  event.title if event else '—',
                'event_date':   event.date.strftime('%d %b %Y') if event and event.date else '—',
            })

        # Sort: checked-in first, then pending, then missed
        status_order = {'checked_in': 0, 'pending': 1, 'missed': 2}
        results.sort(key=lambda r: (status_order.get(r['status'], 3), r['name']))

    else:
        # ── VOLUNTEER: show only their own attendance ──────────────────
        records = AttendanceRecord.query.filter_by(
            volunteer_id=current_user.id
        ).order_by(AttendanceRecord.timestamp.desc()).all()

        seen_event_ids = set()
        for rec in records:
            if rec.event_id in seen_event_ids:
                continue
            seen_event_ids.add(rec.event_id)

            event = Event.query.get(rec.event_id)
            checked_in = rec.status == 'present' or rec.checked_in

            results.append({
                'id':           current_user.id,
                'name':         current_user.name,
                'email':        current_user.email or '',
                'avatar':       current_user.profile_pic or '',
                'xp':           current_user.xp or 0,
                'level':        current_user.level or 1,
                'checked_in':   checked_in,
                'checkin_time': rec.timestamp.strftime('%I:%M %p') if rec.timestamp else None,
                'missed':       False,
                'status':       'checked_in' if checked_in else 'pending',
                'event_id':     rec.event_id,
                'event_title':  event.title if event else '—',
                'event_date':   event.date.strftime('%d %b %Y') if event and event.date else '—',
            })

    return jsonify(results)


# ─── 2. MANUAL CHECK-IN BY HOST ─────────────────────────────────────

@dashboard.route('/checkin/<int:user_id>', methods=['POST'])
@login_required
def manual_checkin_by_user(user_id):
    """
    Host manually marks a volunteer as checked in.
    Finds the most recent active/recent event this volunteer booked.
    """
    from app.models import User, AttendanceRecord, Event, Booking

    volunteer = User.query.get_or_404(user_id)

    # Find events this host created
    host_event_ids = [
        e.id for e in Event.query.filter_by(creator_id=current_user.id).all()
    ]

    if not host_event_ids:
        return jsonify({'success': False, 'message': 'You have no events'})

    # Find volunteer's booking for one of host's events
    booking = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.event_id.in_(host_event_ids)
    ).order_by(Booking.id.desc()).first()

    # If no booking, try to find an attendance record directly
    if not booking:
        att_direct = AttendanceRecord.query.filter(
            AttendanceRecord.volunteer_id == user_id,
            AttendanceRecord.event_id.in_(host_event_ids)
        ).order_by(AttendanceRecord.id.desc()).first()

        if att_direct:
            event_id = att_direct.event_id
        else:
            # Last resort: use the most recent host event
            latest_event = Event.query.filter(
                Event.id.in_(host_event_ids)
            ).order_by(Event.date.desc()).first()

            if not latest_event:
                return jsonify({'success': False, 'message': 'No event found'})
            event_id = latest_event.id
    else:
        event_id = booking.event_id

    # Check if already checked in
    existing = AttendanceRecord.query.filter_by(
        volunteer_id=user_id,
        event_id=event_id
    ).first()

    now = datetime.utcnow()
    now_str = now.strftime('%I:%M %p')

    if existing:
        if existing.status == 'present' or existing.checked_in:
            return jsonify({'success': False, 'message': 'Already checked in'})
        # Update
        existing.status    = 'present'
        existing.checked_in = True
        existing.timestamp = now
    else:
        record = AttendanceRecord(
            volunteer_id = user_id,
            event_id     = event_id,
            timestamp    = now,
            status       = 'present',
            checked_in   = True,
            task_assigned = True
        )
        db.session.add(record)

    db.session.commit()

    # Emit Socket.IO so all connected hosts see the update
    try:
        socketio.emit('new_checkin', {
            'id':   user_id,
            'name': volunteer.name,
            'time': now_str,
            'xp':   volunteer.xp or 0
        }, broadcast=True)
    except Exception as e:
        pass  # Don't fail if socket not available

    return jsonify({
        'success':      True,
        'message':      f'{volunteer.name} checked in successfully',
        'checkin_time': now_str
    })


# ─── 3. API — LEADERBOARD (needed by XP progress page too) ──────────

@dashboard.route('/api/leaderboard')
@login_required
def api_leaderboard():
    """REST fallback for leaderboard (used by xp_progress page)"""
    from app.models import User
    top = User.query.filter_by(role='volunteer')\
                    .order_by(User.xp.desc())\
                    .limit(20).all()
    return jsonify([{
        'name':  u.name,
        'xp':    u.xp or 0,
        'level': u.level or 1,
    } for u in top])

    
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

@dashboard.route('/weekly-goals')
@login_required
def weekly_goals():
    from app.models import Goal
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.deadline.asc()).all()
    return render_template("volunteer/weekly_goals.html", goals=goals)

@dashboard.route('/api/goals')
@login_required
def api_goals():
    from app.models import Goal, GoalTask
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.deadline.asc()).all()
    result = []
    for g in goals:
        gdict = g.to_dict()
        tasks = GoalTask.query.filter_by(goal_id=g.id).order_by(GoalTask.order.asc()).all()
        gdict['tasks'] = [t.to_dict() for t in tasks]
        result.append(gdict)
    return jsonify(result)

@dashboard.route('/my_goal_tasks/<int:goal_id>')
@login_required
def my_goal_tasks(goal_id):
    from app.models import Goal, GoalTask
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id and current_user.role != 'host':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    tasks = GoalTask.query.filter_by(goal_id=goal_id).order_by(GoalTask.order.asc()).all()
    return jsonify({'success': True, 'tasks': [t.to_dict() for t in tasks]})

@dashboard.route('/submit_goal_task_proof/<int:task_id>', methods=['POST'])
@login_required
def submit_goal_task_proof(task_id):
    from app.models import Goal, GoalTask, XPLog
    task = GoalTask.query.get_or_404(task_id)
    goal = Goal.query.get(task.goal_id)
    
    if goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    proof = request.files.get('proof')
    if not proof or proof.filename == '':
        return jsonify({'success': False, 'message': 'No image uploaded'})

    import os
    from werkzeug.utils import secure_filename
    filename = secure_filename(f"goal_{current_user.id}_{task_id}_{proof.filename}")
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    proof.save(filepath)

    # ── AI Auto-Pass logic (simulated) ──
    ai_verified = True
    confidence = 90.0
    xp_earned = 0

    if task.status != 'verified':
        task.proof_image = filename
        task.ai_verified = True
        task.status = 'verified'
        task.completed_at = datetime.utcnow()
        
        xp_earned = task.xp_reward or 10
        current_user.xp = (current_user.xp or 0) + xp_earned
        
        log = XPLog(user_id=current_user.id, xp=xp_earned, reason=f'Goal Task proof: {task.title}')
        db.session.add(log)
        
        # Update goal progress
        all_tasks = GoalTask.query.filter_by(goal_id=goal.id).all()
        verified_count = sum(1 for t in all_tasks if t.status == 'verified')
        goal.progress = round((verified_count / len(all_tasks)) * 100) if all_tasks else 0
        if goal.progress >= 100:
            goal.status = 'Completed'
            goal.completed_at = datetime.utcnow()

    db.session.commit()
    return jsonify({
        'success': True,
        'ai_verified': ai_verified,
        'confidence': round(confidence),
        'xp_earned': xp_earned,
        'total_xp': current_user.xp
    })

@dashboard.route('/check_goal_completion/<int:goal_id>')
@login_required
def check_goal_completion(goal_id):
    from app.models import Goal, GoalTask
    goal = Goal.query.get_or_404(goal_id)
    all_tasks = GoalTask.query.filter_by(goal_id=goal_id).all()
    complete = all(t.status == 'verified' for t in all_tasks) if all_tasks else False
    
    return jsonify({
        'complete': complete,
        'total_xp': sum(t.xp_reward for t in all_tasks if t.status == 'verified'),
        'grand_total_xp': current_user.xp
    })



# ── 3. SET WEEKLY GOAL — UPDATED to also create GoalTask rows ───────

# In set_weekly_goal(), after parsing form data, REPLACE the loop with:

# if request.method == "POST":
#     ...parse title, description, deadline, priority, tags, quote...
#
#     # Parse tasks from JSON
#     import json as _json
#     tasks_raw = request.form.get("tasks_data", "[]")
#     try:
#         tasks_list = _json.loads(tasks_raw)
#     except Exception:
#         tasks_list = []
#
#     goals_to_add = []
#     for v in volunteers:
#         goal = Goal(
#             user_id=v.id,
#             title=title,
#             description=description,
#             deadline=deadline_date,
#             priority=priority,
#             tags=tags,
#             quote=quote,
#             status="Pending"
#         )
#         db.session.add(goal)
#         db.session.flush()  # get goal.id
#
#         # Add tasks for this volunteer's goal
#         for i, t in enumerate(tasks_list, start=1):
#             task = GoalTask(
#                 goal_id=goal.id,
#                 title=t.get('title', ''),
#                 description=t.get('desc', ''),
#                 xp_reward=int(t.get('xp', 10)),
#                 order=i,
#                 status='pending',
#                 completed=False
#             )
#             db.session.add(task)
#
#     db.session.commit()
#     flash(f"Weekly goal + {len(tasks_list)} tasks assigned to {total_volunteers} volunteers!", "success")
#     return redirect(url_for("dashboard.set_weekly_goal"))


# ── 4. GoalTask MODEL — add to app/models.py ────────────────────────

# class GoalTask(db.Model):
#     __tablename__ = 'goal_task'
#     id           = db.Column(db.Integer, primary_key=True)
#     goal_id      = db.Column(db.Integer, db.ForeignKey('goal.id'), nullable=False)
#     title        = db.Column(db.String(200), nullable=False)
#     description  = db.Column(db.Text, nullable=True)
#     xp_reward    = db.Column(db.Integer, default=10)
#     order        = db.Column(db.Integer, default=1)
#     status       = db.Column(db.String(20), default='pending')   # 'pending' | 'completed'
#     completed    = db.Column(db.Boolean, default=False)
#     completed_at = db.Column(db.DateTime, nullable=True)
#
#     goal = db.relationship('Goal', backref=db.backref('tasks', lazy=True, order_by='GoalTask.order'))
#
#     def to_dict(self):
#         return {
#             'id':           self.id,
#             'goal_id':      self.goal_id,
#             'title':        self.title,
#             'description':  self.description or '',
#             'xp_reward':    self.xp_reward or 10,
#             'order':        self.order,
#             'status':       self.status or 'pending',
#             'completed':    self.completed or False,
#             'completed_at': self.completed_at.isoformat() if self.completed_at else None,
#         }


# ── 5. MIGRATION COMMAND (run once in Flask shell) ──────────────────

# from app import db
# db.create_all()   # Creates goal_task table if it doesn't exist
# print("✅ GoalTask table created!")

# ── 3. MARK COMPLETE ENDPOINT ────────────────────────────────


# ── 4. FIXED SOCKET.IO HANDLER ───────────────────────────────

# REPLACE the existing @socketio.on("get_goals") handler with this:

@socketio.on("get_goals")
def handle_get_goals():
    from app.models import Goal
    from flask_login import current_user

    if not current_user.is_authenticated:
        emit("update_goals", [])
        return

    # ✅ Fetch goals assigned to THIS volunteer
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.deadline.asc()).all()

    goal_data = [g.to_dict() for g in goals]

    emit("update_goals", goal_data)


# ── 5. HOW HOST ASSIGNS GOALS ────────────────────────────────
#
# Your existing set_weekly_goal() route does:
#
#   for v in volunteers:
#       goals_to_add.append(Goal(user_id=v.id, title=title, ...))
#   db.session.bulk_save_objects(goals_to_add)
#
# This is CORRECT — one row per volunteer with user_id = volunteer.id
# So when the volunteer fetches /api/goals or socket emits get_goals,
# they get their own rows.
#
# If volunteers are seeing 0 goals, the issue is:
#   a) The old template had no Jinja fallback (NOW FIXED in weekly_goals.html)
#   b) Socket.IO 'get_goals' event wasn't being emitted after connect
#      (NOW FIXED — the template emits it on socket 'connect' event AND
#       has a 2.5s HTTP fallback timeout)
#   c) Goal.to_dict() wasn't defined → NOW using it from models.py
#      (your Goal model already has to_dict() defined — confirmed in models.py)


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

# Explore All Missions Route
@dashboard.route('/explore-missions')
@login_required
def explore_missions():
    archive_expired_events()
    
    # Fetch all unarchived events without distance filtering initially
    all_events = Event.query.filter_by(archived=False).order_by(Event.date.asc()).all()
    
    event_data = []
    try:
        user_loc = (float(current_user.latitude), float(current_user.longitude))
    except Exception:
        user_loc = None

    for event in all_events:
        dist_str = "Calculating..."
        if user_loc and event.latitude and event.longitude:
            try:
                dist_km = geodesic((event.latitude, event.longitude), user_loc).km
                dist_str = f"{dist_km:.1f} km away"
            except Exception:
                pass

        booking = Booking.query.filter_by(event_id=event.id, user_id=current_user.id).first()
        attendance = AttendanceRecord.query.filter_by(event_id=event.id, volunteer_id=current_user.id).first()

        status = {
            "booked": bool(booking),
            "checked_in": bool(attendance and attendance.checked_in),
            "task_started": bool(attendance and attendance.task_started),
            "task_completed": bool(attendance and attendance.task_completed)
        }

        event_data.append({
            "event": event,
            "status": status,
            "distance_str": dist_str
        })

    return render_template('explore_missions.html', events=event_data, user=current_user)


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


# ─────────────────────────────────────────────────────────────
# REPLACE your existing /certificates route in dashboard.py
# ─────────────────────────────────────────────────────────────

@dashboard.route('/certificates')
@login_required
def certificates():
    selected_event = request.args.get('event', None)

    # ✅ Only get attendance records where task is COMPLETED
    query = (
        db.session.query(AttendanceRecord)
        .join(User, AttendanceRecord.volunteer_id == User.id)
        .join(Event, AttendanceRecord.event_id == Event.id)
        .filter(AttendanceRecord.task_completed == True)  # ← KEY FILTER
    )

    # ✅ If host: show all volunteers who completed tasks in their events
    # ✅ If volunteer: show only their own completed tasks
    if current_user.role == 'volunteer':
        query = query.filter(AttendanceRecord.volunteer_id == current_user.id)
    else:
        # Host sees completions only for events they created
        host_event_ids = [e.id for e in Event.query.filter_by(creator_id=current_user.id).all()]
        query = query.filter(AttendanceRecord.event_id.in_(host_event_ids))

    if selected_event:
        query = query.filter(Event.title == selected_event)

    attendance_records = query.all()

    participants = []
    for record in attendance_records:
        # Get XP earned from Booking
        booking = Booking.query.filter_by(
            user_id=record.volunteer_id,
            event_id=record.event_id
        ).first()
        xp_earned = booking.xp_earned if booking else 0
        issued_date = booking.completed_time.strftime('%d %B %Y') if booking and booking.completed_time else 'N/A'

        participants.append({
            'name':         record.volunteer.name,
            'volunteer_id': record.volunteer_id,
            'event':        record.event.title,
            'event_id':     record.event_id,
            'hours':        record.calculated_hours,
            'xp_earned':    xp_earned,
            'issued_date':  issued_date,
        })

    events = Event.query.all()

    return render_template(
        'certificates.html',
        participants=participants,
        events=events,
        selected_event=selected_event,
        now=datetime.now()
    )

# ─────────────────────────────────────────────────────────────
# REPLACE your impact_timeline route in dashboard.py with this
# (search for "def impact_timeline" — may appear twice, keep only this one)
# ─────────────────────────────────────────────────────────────

@dashboard.route('/impact-timeline', endpoint='impact_timeline')
@login_required
def impact_timeline():
    from app.models import XPLog, AttendanceRecord, UserBadge, Badge, Event, Booking

    entries = []

    # ── 1. XP Logs ──────────────────────────────────────────
    xp_logs = XPLog.query.filter_by(user_id=current_user.id)\
                         .order_by(XPLog.timestamp.desc()).all()
    for log in xp_logs:
        entries.append({
            'icon':        'lightning-charge-fill',
            'color':       'warning',
            'title':       f'Earned {log.xp} XP',
            'description': log.reason or 'XP awarded',
            'date':        log.timestamp.strftime('%d %b %Y, %I:%M %p'),
            'timestamp':   log.timestamp
        })

    # ── 2. Event Check-ins ───────────────────────────────────
    attendance = AttendanceRecord.query.filter_by(volunteer_id=current_user.id)\
                                       .order_by(AttendanceRecord.timestamp.desc()).all()
    for rec in attendance:
        event = Event.query.get(rec.event_id)
        if event:
            entries.append({
                'icon':        'geo-alt-fill',
                'color':       'primary',
                'title':       f'Checked in: {event.title}',
                'description': f'Location: {event.location}',
                'date':        rec.timestamp.strftime('%d %b %Y, %I:%M %p'),
                'timestamp':   rec.timestamp
            })

        # Task completed entry
        if rec.task_completed:
            entries.append({
                'icon':        'patch-check-fill',
                'color':       'success',
                'title':       f'Completed tasks: {event.title if event else "Event"}',
                'description': 'All tasks finished — certificate unlocked! 🎉',
                'date':        rec.timestamp.strftime('%d %b %Y, %I:%M %p'),
                'timestamp':   rec.timestamp
            })

    # ── 3. Badges Earned ────────────────────────────────────
    user_badges = UserBadge.query.filter_by(user_id=current_user.id)\
                                  .order_by(UserBadge.awarded_at.desc()).all()
    for ub in user_badges:
        badge = Badge.query.get(ub.badge_id)
        if badge:
            entries.append({
                'icon':        'award-fill',
                'color':       'danger',
                'title':       f'Badge Unlocked: {badge.name}',
                'description': badge.description or 'New badge earned!',
                'date':        ub.awarded_at.strftime('%d %b %Y, %I:%M %p'),
                'timestamp':   ub.awarded_at
            })

    # ── 4. Bookings ─────────────────────────────────────────
    bookings = Booking.query.filter_by(user_id=current_user.id)\
                             .order_by(Booking.timestamp.desc()).all()
    for b in bookings:
        event = Event.query.get(b.event_id)
        if event:
            entries.append({
                'icon':        'calendar-check-fill',
                'color':       'info',
                'title':       f'Booked: {event.title}',
                'description': f'Scheduled on {event.date.strftime("%d %b %Y")}',
                'date':        b.timestamp.strftime('%d %b %Y, %I:%M %p'),
                'timestamp':   b.timestamp
            })

    # Sort all entries newest first
    entries.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template('impact_timeline.html', impact_entries=entries)
@dashboard.route('/help-center', endpoint='help_center')
@login_required
def help_center():
    return render_template('help_center.html')

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


from datetime import datetime, date, timedelta
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db

@dashboard.route("/set-weekly-goal", methods=["GET", "POST"])
@login_required
def set_weekly_goal():
    if current_user.role != "host":
        flash("Only hosts can set goals.", "danger")
        return redirect(url_for("dashboard.home"))

    from app.models import User, Goal

    # 🔥 GET ALL VOLUNTEERS (ACTIVE ONLY if you have field)
    volunteers = User.query.filter_by(role="volunteer").all()
    total_volunteers = len(volunteers)

    # 🔥 TODAY + WEEK RANGE
    today = datetime.utcnow()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)
    current_week_range = f"{start_week.strftime('%d %b')} - {end_week.strftime('%d %b %Y')}"

    # 🔥 HANDLE POST
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        deadline = request.form.get("deadline")
        priority = request.form.get("priority") or "Low"
        tags = request.form.get("tags")
        quote = request.form.get("quote")

        # ✅ basic validation
        if not title or not deadline:
            flash("Title and deadline are required!", "danger")
            return redirect(url_for("dashboard.set_weekly_goal"))

        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d")
        except:
            deadline_date = None

        import json as _json
        tasks_raw = request.form.get("tasks_data", "[]")
        try:
            tasks_list = _json.loads(tasks_raw)
        except Exception:
            tasks_list = []

        # 🚀 ADD GOALS + TASKS FOR EACH VOLUNTEER
        from app.models import GoalTask
        for v in volunteers:
            goal = Goal(
                user_id=v.id,
                title=title,
                description=description,
                deadline=deadline_date,
                priority=priority,
                tags=tags,
                quote=quote,
                status="Pending"
            )
            db.session.add(goal)
            db.session.flush()  # Get goal.id

            # Attach tasks
            for i, t in enumerate(tasks_list, start=1):
                task = GoalTask(
                    goal_id=goal.id,
                    title=t.get('title', 'Goal Task'),
                    description=t.get('desc', ''),
                    xp_reward=int(t.get('xp', 10)),
                    order=i,
                    status='pending'
                )
                db.session.add(task)

        db.session.commit()

        flash(f"Weekly goal + {len(tasks_list)} tasks assigned to {total_volunteers} volunteers!", "success")
        return redirect(url_for("dashboard.set_weekly_goal"))

    # 🔥 FETCH EXISTING GOALS (for table + stats)
    goals = Goal.query.order_by(Goal.created_at.desc()).all()

    # ✅ FINAL RENDER (IMPORTANT FIX)
    return render_template(
        "host/set_weekly_goal.html",
        volunteers=volunteers,
        total_volunteers=total_volunteers,
        goals=goals,
        today=today,
        current_week_range=current_week_range
    )

@dashboard.route("/delete-goal/<int:goal_id>", methods=["POST"])
@login_required
def delete_goal(goal_id):
    from app.models import Goal

    goal = Goal.query.get_or_404(goal_id)

    # 🔒 Optional security (host only)
    if current_user.role != "host":
        flash("Unauthorized action", "danger")
        return redirect(url_for("dashboard.home"))

    db.session.delete(goal)
    db.session.commit()

    flash("Goal deleted successfully!", "success")
    return redirect(url_for("dashboard.set_weekly_goal"))

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
# ══════════════════════════════════════════════════════════════
#  COMPLETE FIX — paste these into your files
#  1. app/forms.py  →  BadgeForm class
#  2. app/dashboard.py  →  create_badge route
# ══════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────
# 1.  app/forms.py  — replace / add BadgeForm
# ──────────────────────────────────────────────────────────────

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField,
    IntegerField, HiddenField, SubmitField
)
from wtforms.validators import DataRequired, Optional, NumberRange, Length


class BadgeForm(FlaskForm):
    # ── Basic info ────────────────────────────────────────────
    name = StringField(
        'Badge Name',
        validators=[DataRequired(), Length(max=100)]
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)]
    )
    level = SelectField(
        'Level',
        choices=[
            ('beginner',     '🌱 Beginner'),
            ('intermediate', '⚡ Intermediate'),
            ('pro',          '🔥 Pro'),
        ],
        validators=[DataRequired()]
    )

    # ── Image ─────────────────────────────────────────────────
    image_file = FileField(
        'Upload Image',
        validators=[
            Optional(),
            FileAllowed(['jpg', 'jpeg', 'png', 'svg', 'webp'], 'Images only!')
        ]
    )
    image_url = StringField('Image URL', validators=[Optional(), Length(max=500)])

    # ── Tags (comma-separated string; chips are just UI sugar) ─
    tags = StringField('Tags', validators=[Optional(), Length(max=300)])

    # ── XP reward ─────────────────────────────────────────────
    xp_reward = IntegerField(
        'XP Reward',
        validators=[Optional(), NumberRange(min=0, max=10000)],
        default=100
    )

    # ── Condition — NOTE: rendered as plain <select> in the
    #    template, so we read it from request.form directly.
    #    We keep a HiddenField here so WTForms doesn't choke. ──
    condition_type  = HiddenField('Condition Type',  default='event_attendance')
    condition_value = IntegerField(
        'Condition Value',
        validators=[Optional(), NumberRange(min=1)],
        default=3
    )

    submit = SubmitField('Create Badge')


# ──────────────────────────────────────────────────────────────
# 2.  app/dashboard.py  — replace create_badge() entirely
# ──────────────────────────────────────────────────────────────

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import db, Badge
from app.utils.decorators import roles_required
from app.forms import BadgeForm
import os


@dashboard.route('/host/create-badge', methods=['GET', 'POST'])
@login_required
@roles_required('host')
def create_badge():
    form = BadgeForm()

    if request.method == 'POST':
        # ── 1. Pull every value straight from request.form / files ──
        #    This is the safest approach: it works whether WTForms
        #    validation passes or not, and avoids field-name mismatches.

        name            = request.form.get('name', '').strip()
        description     = request.form.get('description', '').strip()
        level           = request.form.get('level', 'beginner').strip()
        xp_reward_raw   = request.form.get('xp_reward', '100').strip()
        tags_raw        = request.form.get('tags_raw', '').strip()  # chip-input hidden field
        if not tags_raw:
            tags_raw    = request.form.get('tags', '').strip()      # fallback

        # condition_type comes from the plain <select> OR the hidden field
        condition_type  = (
            request.form.get('condition_type_select') or      # plain <select name="condition_type_select">
            request.form.get('conditionTypeSelect') or
            request.form.get('condition_type') or             # hidden field synced by JS
            'event_attendance'
        ).strip()

        condition_value_raw = request.form.get('condition_value', '3').strip()

        # ── 2. Validate required fields ──────────────────────
        if not name:
            flash('Badge name is required.', 'danger')
            badges = Badge.query.filter_by(created_by=current_user.id).all()
            return render_template('host/create_badge.html', form=form, badges=badges)

        # ── 3. Safe type-cast ────────────────────────────────
        try:
            xp_reward = int(xp_reward_raw)
        except (ValueError, TypeError):
            xp_reward = 100

        try:
            condition_value = int(condition_value_raw)
        except (ValueError, TypeError):
            condition_value = 3

        # ── 4. Handle image upload vs URL ────────────────────
        image_url = '/static/badges/default.png'          # sensible default

        uploaded_file = request.files.get('image_file')
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'badges')
            os.makedirs(upload_dir, exist_ok=True)
            save_path = os.path.join(upload_dir, filename)
            uploaded_file.save(save_path)
            image_url = f'/static/badges/{filename}'
        else:
            # Try URL field (typed URL or emoji set by JS)
            url_field = request.form.get('image_url_input', '').strip()
            if not url_field:
                url_field = request.form.get('imageUrlInput', '').strip()
            if url_field:
                image_url = url_field

        # ── 5. Create and persist the Badge ──────────────────
        badge = Badge(
            name            = name,
            description     = description,
            image_url       = image_url,
            condition_type  = condition_type,
            condition_value = condition_value,
            created_by      = current_user.id,
            level           = level,
            tags            = tags_raw,
            xp_reward       = xp_reward,
        )
        db.session.add(badge)
        db.session.commit()

        flash(f'✅ Badge "{name}" created successfully! (+{xp_reward} XP)', 'success')
        return redirect(url_for('dashboard.create_badge'))

    # ── GET: show the form + existing badges ─────────────────
    badges = Badge.query.filter_by(created_by=current_user.id).order_by(Badge.id.desc()).all()
    return render_template('host/create_badge.html', form=form, badges=badges)


# ──────────────────────────────────────────────────────────────
# 3.  TEMPLATE FIX — in create_badge.html
#
#  The condition <select> must have name="condition_type" so the
#  server can read it from request.form.  Change the select tag:
#
#    FROM:
#      <select class="select" id="conditionTypeSelect" onchange="syncCondition()">
#
#    TO:
#      <select class="select" name="condition_type" id="conditionTypeSelect" onchange="syncCondition()">
#
#  And the image URL input must have a name attribute:
#
#    FROM:
#      <input class="input" type="url" id="imageUrlInput" ...>
#
#    TO:
#      <input class="input" type="url" id="imageUrlInput" name="image_url_input" ...>
#
#  That's it — everything else in the template is already correct.
# ──────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 2 — bulk_badge_upload  (also fixed)
# ─────────────────────────────────────────────────────────────────────────────

@dashboard.route('/host/bulk-badge-upload', methods=['POST'])
@login_required
@roles_required('host')
def bulk_badge_upload():
    import csv, io

    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(request.referrer or url_for('dashboard.create_badge'))

    stream    = io.StringIO(file.stream.read().decode('UTF-8'), newline=None)
    csv_input = csv.DictReader(stream)

    created = 0
    skipped = 0

    for row in csv_input:
        try:
            badge_name = (row.get('name') or '').strip()
            if not badge_name:
                skipped += 1
                continue

            badge = Badge(
                name            = badge_name,
                description     = (row.get('description') or '').strip(),
                level           = (row.get('level') or 'beginner').strip(),
                tags            = (row.get('tags') or '').strip(),
                xp_reward       = int(row.get('xp_reward') or 0),
                condition_type  = (row.get('condition_type') or 'event_attendance').strip(),
                condition_value = int(row.get('condition_value') or 0),
                created_by      = current_user.id,
                image_url       = '/static/badges/default.png',
            )
            db.session.add(badge)
            created += 1
        except Exception as e:
            skipped += 1
            current_app.logger.warning(f'CSV row skipped: {e}')

    db.session.commit()
    flash(f'✅ Uploaded {created} badge(s), skipped {skipped}.', 'success' if created else 'warning')
    return redirect(url_for('dashboard.create_badge'))


@dashboard.route('/view_badge')
@login_required
def view_badgess():
    from app.models import Badge, UserBadge, AttendanceRecord, db, User
    from flask_login import current_user

    all_badges = Badge.query.all()
    print("🔥 TOTAL BADGES:", len(all_badges))

    user_badge_ids = [
        ub.badge_id for ub in UserBadge.query.filter_by(user_id=current_user.id).all()
    ]

    earned = []
    locked = []

    for badge in all_badges:
        is_unlocked = badge.id in user_badge_ids
        progress = 100 if is_unlocked else 0

        # ✅ PROGRESS LOGIC
        if not is_unlocked and badge.condition_type and badge.condition_value:

            if badge.condition_type == 'xp':
                user_xp = current_user.xp or 0
                progress = min(int((user_xp / badge.condition_value) * 100), 100)

            elif badge.condition_type == 'task_completed':
                completed = AttendanceRecord.query.filter_by(
                    volunteer_id=current_user.id,
                    task_completed=True
                ).count()
                progress = min(int((completed / badge.condition_value) * 100), 100)

            elif badge.condition_type == 'event_attendance':
                attended = AttendanceRecord.query.filter_by(
                    volunteer_id=current_user.id
                ).count()
                progress = min(int((attended / badge.condition_value) * 100), 100)

            # ✅ AUTO UNLOCK (avoid duplicate insert)
            if progress >= 100 and badge.id not in user_badge_ids:
                new_unlock = UserBadge(
                    user_id=current_user.id,
                    badge_id=badge.id
                )
                db.session.add(new_unlock)
                db.session.commit()
                is_unlocked = True

        # 👤 Creator name
        creator_name = "Host"
        if badge.created_by:
            creator = User.query.get(badge.created_by)
            if creator:
                creator_name = creator.name

        badge_data = {
            'id': badge.id,
            'name': badge.name,
            'description': badge.description,
            'icon_url': badge.image_url or '/static/badges/default.png',  # IMPORTANT (template match)
            'rarity': badge.level or 'Common',
            'xp': badge.xp_reward or 0,
            'category': badge.condition_type or 'General',
            'progress': progress,
            'hint': f"Complete {badge.condition_value} {badge.condition_type}" if badge.condition_value else "",
            'earned_date': None,
            'created_by': creator_name
        }

        if is_unlocked:
            earned.append(badge_data)
        else:
            locked.append(badge_data)

    print("✅ EARNED:", len(earned))
    print("🔒 LOCKED:", len(locked))

    return render_template(
        'view_badges.html',
        badges={
            "earned": earned,
            "locked": locked
        }
    )


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

    # Delete all associated UserBadge records first to prevent SQLite NOT NULL constraint errors
    from app.models import UserBadge
    UserBadge.query.filter_by(badge_id=badge.id).delete()

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


def get_live_stats():
    from app.models import User, Event
    from sqlalchemy import func

    volunteers = User.query.filter_by(role='volunteer').count()
    events = Event.query.count()
    cities = db.session.query(func.count(func.distinct(Event.location))).scalar()

    return {
        "volunteers": volunteers,
        "events": events,
        "cities": cities
    }

def broadcast_stats():
    stats = get_live_stats()
    socketio.emit("update_stats", stats, broadcast=True)


    # ============================================================
#  BADGE XP INTEGRATION — Add this to your routes / utils
#  Works with your existing EcoNova / ReEarth Flask app
# ============================================================

# ── 1. UTILITY FUNCTION (add to utils.py or directly in routes) ──────────────

def award_badge_with_xp(user, badge, db):
    """
    Awards a badge to the user AND adds the badge's XP to their total.
    Call this wherever you currently assign badges.

    Returns: (already_had_badge: bool, xp_gained: int)
    """
    from models import UserBadge, Notification  # adjust import path
    from datetime import datetime

    # Check if already earned
    already = UserBadge.query.filter_by(
        user_id=user.id,
        badge_id=badge.id
    ).first()

    if already:
        return True, 0  # already has it, no duplicate XP

    # ── Award the badge ──
    new_ub = UserBadge(
        user_id=badge.id,          # ← adjust field names to your model
        badge_id=badge.id,
        earned_date=datetime.utcnow()
    )
    # Fix: use correct field
    new_ub.user_id = user.id
    db.session.add(new_ub)

    # ── Add XP to user ──
    xp_gain = badge.xp or 0
    user.xp = (user.xp or 0) + xp_gain  # adjust field name if needed

    # ── Optional: log to Notification / milestone feed ──
    notif = Notification(
        user_id=user.id,
        message=f"🏅 Badge earned: {badge.name} (+{xp_gain} XP)",
        category="badge",
        timestamp=datetime.utcnow()
    )
    db.session.add(notif)

    db.session.commit()
    return False, xp_gain


# ── 2. USAGE EXAMPLE — wherever badge is awarded in your routes ───────────────

# BEFORE (your old code probably looked like this):
# user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
# db.session.add(user_badge)
# db.session.commit()

# AFTER (replace with):
# already_had, xp_earned = award_badge_with_xp(user, badge, db)
# if not already_had:
#     flash(f"🏅 Badge Unlocked! +{xp_earned} XP", "success")


# ── 3. AUTO-BADGE CHECK FUNCTION — call after every XP-earning action ─────────

def check_and_award_badges(user, db):
    """
    Checks all badge conditions for the user and awards any newly qualified ones.
    Call this after: task complete, quiz correct, event check-in, etc.
    """
    from models import Badge, UserBadge  # adjust import

    all_badges = Badge.query.all()

    awarded = []
    for badge in all_badges:
        already_earned = UserBadge.query.filter_by(
            user_id=user.id,
            badge_id=badge.id
        ).first()
        if already_earned:
            continue

        # ── XP-based badge conditions ──
        qualifies = False

        if badge.category == "XP":
            # e.g. badge.required_xp = 100, 500, 1000 etc.
            if badge.required_xp and user.xp >= badge.required_xp:
                qualifies = True

        elif badge.category == "Milestone":
            # e.g. badge.required_events = 5
            if badge.required_events:
                from models import EventAttendance
                count = EventAttendance.query.filter_by(user_id=user.id).count()
                if count >= badge.required_events:
                    qualifies = True

        elif badge.category == "Event":
            # custom event-specific logic
            pass

        # Add more category conditions as needed

        if qualifies:
            _, xp_earned = award_badge_with_xp(user, badge, db)
            awarded.append((badge.name, xp_earned))

    return awarded  # list of (badge_name, xp_gained)


# ── 4. CALL check_and_award_badges in your XP-awarding route ─────────────────

# Example: wherever user earns XP (task submission, quiz, check-in etc.)
#
# @volunteer_bp.route('/submit-task', methods=['POST'])
# @login_required
# def submit_task():
#     ...
#     # Award XP for task
#     current_user.xp += task_xp
#     db.session.commit()
#
#     # ← ADD THIS after XP update:
#     newly_awarded = check_and_award_badges(current_user, db)
#     for badge_name, xp in newly_awarded:
#         flash(f"🏅 New Badge: {badge_name} (+{xp} XP)!", "success")
#         # Socket.IO emit (if using real-time):
#         # socketio.emit('badge_unlocked', {'name': badge_name, 'xp': xp}, room=str(current_user.id))
#
#     return redirect(url_for('volunteer.dashboard'))


# ── 5. BADGE MODEL — make sure your Badge model has these fields ──────────────

# class Badge(db.Model):
#     id          = db.Column(db.Integer, primary_key=True)
#     name        = db.Column(db.String(100))
#     description = db.Column(db.Text)
#     icon_url    = db.Column(db.String(255))
#     category    = db.Column(db.String(50))   # XP / Event / Milestone
#     rarity      = db.Column(db.String(50))   # Common/Rare/Epic/Legendary
#     xp          = db.Column(db.Integer, default=0)     # XP badge gives when earned
#     required_xp = db.Column(db.Integer, nullable=True)  # XP needed to unlock this badge


# ── 6. SOCKET.IO REAL-TIME UNLOCK (optional) ─────────────────────────────────

# In award_badge_with_xp(), after db.session.commit(), add:
#
# from extensions import socketio   # your extensions.py
# socketio.emit('badge_unlocked', {
#     'name': badge.name,
#     'xp':   xp_gain,
#     'icon': badge.icon_url
# }, room=str(user.id))
#
# This triggers the JS toast on the Badge Collection page instantly!


# ── 7. XP PROGRESS ROUTE — update to include badge XP in history ─────────────

# In your xp_progress route, the milestone_timeline already shows task/quiz XP.
# To also show badge awards in the timeline, log them as Notification or
# a dedicated XPLog model:
#
# class XPLog(db.Model):
#     id        = db.Column(db.Integer, primary_key=True)
#     user_id   = db.Column(db.Integer, db.ForeignKey('user.id'))
#     amount    = db.Column(db.Integer)
#     reason    = db.Column(db.String(200))  # "Badge: First Steps"
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@dashboard.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    user = current_user

    db.session.delete(user)
    db.session.commit()

    flash("Your account has been deleted.", "danger")
    return redirect(url_for('auth.login'))

# 🔥 ADD THIS FUNCTION
def emit_full_user_update(user):
    xp_for_next = user.level * 100
    xp_percent = int((user.xp / xp_for_next) * 100)

    socketio.emit('user_full_update', {
        'xp': user.xp,
        'level': user.level,
        'xp_percent': xp_percent,
        'xp_for_next_level': xp_for_next,
        'next_level': user.level + 1,
        'xp_remaining': xp_for_next - user.xp,
        'tasks': user.tasks_completed,
        'events': user.events_joined,
        'hours': user.hours
    }, room=f"user_{user.id}")

# ─────────────────────────────────────────────────────────────
# PASTE THIS as your achievements() route in dashboard.py
# Replaces the existing @dashboard.route('/achievements') block
# ─────────────────────────────────────────────────────────────

@dashboard.route('/achievements')
@login_required
def achievements():
    from app.models import UserBadge, Badge, AttendanceRecord

    # ── 1. Earned badges: list of (UserBadge, Badge) tuples ──
    earned_badges = (
        db.session.query(UserBadge, Badge)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .filter(UserBadge.user_id == current_user.id)
        .all()
    )

    # ── 2. Summary stats (real numbers from DB) ──────────────
    total_events = AttendanceRecord.query.filter_by(
        volunteer_id=current_user.id
    ).count()

    total_hours = sum(
        rec.calculated_hours or 0
        for rec in AttendanceRecord.query.filter_by(volunteer_id=current_user.id).all()
    )

    total_tasks = AttendanceRecord.query.filter_by(
        volunteer_id=current_user.id,
        task_completed=True
    ).count()

    summary = {
        "events": total_events,
        "hours":  round(total_hours, 1),
        "tasks":  total_tasks,
    }

    # ── 3. XP & level from User model ────────────────────────
    xp           = current_user.xp    or 0
    level        = current_user.level or 1
    xp_for_next  = level * 100          # each level = 100 XP
    # xp_progress = XP within the current level (0..xp_for_next)
    xp_progress  = xp % xp_for_next if xp_for_next > 0 else 0
    xp_percent   = min(100, round((xp_progress / xp_for_next) * 100)) if xp_for_next > 0 else 0

    return render_template(
        'achievements.html',
        user          = current_user,
        earned_badges = earned_badges,   # list of (UserBadge, Badge)
        summary       = summary,         # {events, hours, tasks}
        level         = level,           # int
        xp_progress   = xp_progress,     # XP in current level window
        xp_percent    = xp_percent,      # % to next level (for Jinja fallback)
    )


# ─── New routes that don't already exist ─────────────────────────────────────

@dashboard.route('/volunteer/weekly-goals')
@login_required
def volunteer_weekly_goals():
    """Volunteer page: see all goals assigned to them (with tasks)."""
    from app.models import Goal
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.created_at.desc()).all()
    return render_template(
        'volunteer/weekly_goals.html',
        goals        = goals,
        current_user = current_user,
    )


@dashboard.route('/goals/complete/<int:goal_id>', methods=['POST'])
@login_required
def complete_goal(goal_id):
    """Mark a goal as completed and award XP."""
    from app.models import Goal, XPLog
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if goal.status == 'Completed':
        return jsonify({'success': True, 'status': 'already_done'})

    goal.status       = 'Completed'
    goal.progress     = 100
    goal.completed_at = datetime.utcnow()

    xp_gain = goal.xp_reward or 50
    current_user.xp   = (current_user.xp or 0) + xp_gain
    try:
        log = XPLog(user_id=current_user.id, xp=xp_gain, reason=f'Completed Goal: {goal.title}')
        db.session.add(log)
    except Exception:
        pass
    db.session.commit()

    try:
        socketio.emit('goal_completed', {
            'goal_id': goal.id, 'title': goal.title, 'xp': xp_gain
        }, room=f'user_{current_user.id}')
    except Exception:
        pass

    return jsonify({'success': True, 'xp_earned': xp_gain, 'status': 'ok'})


@dashboard.route('/goals/task-complete/<int:goal_id>/<int:task_id>', methods=['POST'])
@login_required
def complete_goal_task(goal_id, task_id):
    """Mark a specific task within a goal as completed and award XP."""
    from app.models import Goal, GoalTask, XPLog
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    task = GoalTask.query.filter_by(id=task_id, goal_id=goal_id).first_or_404()

    if task.status == 'completed':
        return jsonify({'success': True, 'already_done': True, 'xp_earned': 0})

    task.status       = 'completed'
    task.completed_at = datetime.utcnow()

    # Award task XP
    xp_gain = task.xp_reward or 10
    current_user.xp   = (current_user.xp or 0) + xp_gain
    try:
        log = XPLog(user_id=current_user.id, xp=xp_gain, reason=f'Task: {task.title}')
        db.session.add(log)
    except Exception:
        pass

    # Recalculate goal progress
    all_tasks   = GoalTask.query.filter_by(goal_id=goal_id).all()
    done_count  = sum(1 for t in all_tasks if t.status == 'completed')
    total_count = len(all_tasks)
    goal.progress = int(done_count / total_count * 100) if total_count else 0

    all_done = done_count == total_count
    if all_done and goal.status != 'Completed':
        goal.status       = 'Completed'
        goal.completed_at = datetime.utcnow()
        bonus_xp = goal.xp_reward or 0
        if bonus_xp:
            current_user.xp = (current_user.xp or 0) + bonus_xp
            try:
                bonus_log = XPLog(user_id=current_user.id, xp=bonus_xp,
                                  reason=f'Goal Complete Bonus: {goal.title}')
                db.session.add(bonus_log)
            except Exception:
                pass

    db.session.commit()

    try:
        socketio.emit('task_completed', {
            'task_id': task.id, 'goal_id': goal.id, 'xp': xp_gain
        }, room=f'user_{current_user.id}')
    except Exception:
        pass

    return jsonify({
        'success':        True,
        'xp_earned':      xp_gain,
        'goal_progress':  goal.progress,
        'goal_completed': all_done,
        'all_tasks_done': all_done,
    })
