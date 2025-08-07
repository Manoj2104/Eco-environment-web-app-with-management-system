from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import qrcode
from app.utils.notifications import create_notification

from .models import Event, Booking, AttendanceRecord, db
from .badge_utils import check_and_award_badges

events = Blueprint('events', __name__)

# ✅ Manage Events
@events.route('/manage-events')
@login_required
def manage_events():
    user_events = Event.query.filter_by(creator_id=current_user.id).all()
    now = datetime.now()

    # ✅ Dummy data to prevent Undefined error
    activity_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    activity_data = [3, 5, 2, 4, 6, 1, 0]

    return render_template(
        'manage_events.html',
        events=user_events,
        now=now,
        activity_labels=activity_labels,
        activity_data=activity_data
    )



# ✅ Create Event (with QR generation)
@events.route('/create-event', methods=['GET', 'POST'])
@login_required
def create_event():
    if request.method == 'POST':
        title = request.form['title']
        location = request.form['location']
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        date_str = request.form['date']
        description = request.form['description']
        thumbnail = request.files.get('thumbnail')
        passcode = request.form.get('passcode')

        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('❌ Invalid date format.', 'danger')
            return redirect(url_for('events.create_event'))

        # Save thumbnail
        thumbnail_filename = None
        if thumbnail and thumbnail.filename:
            thumbnail_filename = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join(current_app.config['UPLOAD_FOLDER'], thumbnail_filename))

        # Generate QR code
        qr_filename = None
        if passcode:
            qr_img = qrcode.make(passcode)
            qr_filename = f"qr_{datetime.utcnow().timestamp()}.png"
            qr_path = os.path.join(current_app.static_folder, 'qr_codes', qr_filename)
            os.makedirs(os.path.dirname(qr_path), exist_ok=True)
            qr_img.save(qr_path)

        # Create event
        new_event = Event(
            title=title,
            location=location,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            date=date,
            description=description,
            thumbnail=thumbnail_filename,
            creator_id=current_user.id,
            passcode=passcode,
            qr_code=qr_filename
        )

        db.session.add(new_event)
        db.session.commit()

        # ✅ Notify nearby volunteers
        if new_event.latitude and new_event.longitude:
            event_location = (new_event.latitude, new_event.longitude)
            volunteers = User.query.filter_by(role='volunteer').all()

            for volunteer in volunteers:
                if volunteer.latitude and volunteer.longitude:
                    user_location = (volunteer.latitude, volunteer.longitude)
                    distance = geodesic(event_location, user_location).km
                    print(f"📍 Volunteer {volunteer.name} is {distance:.2f} km away")

                    if distance <= 10:  # ✅ Within 10 km
                        notification = Notification(
                            user_id=volunteer.id,
                            title=f"Nearby Event: {new_event.title}",
                            message=f"An event near you is happening on {new_event.date.strftime('%d %b %Y')}.",
                            icon='geo-alt-fill'
                        )
                        db.session.add(notification)
                        db.session.commit()

                        # ✅ Real-time emit
                        socketio.emit('new_notification', {
                            'id': notification.id,
                            'title': notification.title,
                            'message': notification.message,
                            'timestamp': notification.timestamp.strftime('%d %b %Y'),
                            'icon': notification.icon
                        }, room=f"user_{volunteer.id}")

        # ✅ Badge system
        awarded = check_and_award_badges(current_user)
        if awarded:
            flash(f"🏅 New badge(s): {', '.join(awarded)}", "info")

        flash('✅ Event created successfully!', 'success')
        return redirect(url_for('dashboard.home'))

    return render_template('create_event.html')



# ✅ Book Event (AJAX)
@events.route('/book_event/<int:event_id>', methods=['POST'])
@login_required
def book_event(event_id):
    create_notification(current_user.id, "Event Booked", f"You successfully booked the event #{event_id}.")
    event = Event.query.get_or_404(event_id)
    appointment_time = request.form.get('appointment_time')
    message = request.form.get('message', '')

    try:
        appointment_time = datetime.strptime(appointment_time, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        try:
            appointment_time = datetime.strptime(appointment_time, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format'})

    if Booking.query.filter_by(user_id=current_user.id, event_id=event_id).first():
        return jsonify({'success': False, 'message': 'Already booked'})

    booking = Booking(
        user_id=current_user.id,
        event_id=event_id,
        appointment_time=appointment_time,
        message=message
    )

    db.session.add(booking)
    db.session.commit()

    awarded = check_and_award_badges(current_user) or []
    return jsonify({'success': True, 'awarded': awarded})


# ✅ Manual Check-In
@events.route('/check_in/<int:event_id>', methods=['POST'])
@login_required
def check_in(event_id):
    event = Event.query.get_or_404(event_id)

    if AttendanceRecord.query.filter_by(event_id=event_id, volunteer_id=current_user.id).first():
        return jsonify({'success': False, 'message': 'Already checked in'})

    checkin = AttendanceRecord(
        event_id=event_id,
        volunteer_id=current_user.id,
        timestamp=datetime.utcnow()
    )

    db.session.add(checkin)
    db.session.commit()

    awarded = check_and_award_badges(current_user) or []
    return jsonify({'success': True, 'awarded': awarded})


# ✅ Passcode Verification Check-In
@events.route('/verify_checkin', methods=['POST'])
@login_required
def verify_checkin():
    event_id = request.form.get('event_id')
    input_code = request.form.get('passcode')

    event = Event.query.get(event_id)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'})

    if input_code and input_code.strip() == (event.passcode or '').strip():
        already_checked = AttendanceRecord.query.filter_by(event_id=event.id, volunteer_id=current_user.id).first()
        if already_checked:
            return jsonify({'success': False, 'error': 'Already checked in'})

        new_attendance = AttendanceRecord(
            event_id=event.id,
            volunteer_id=current_user.id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_attendance)
        db.session.commit()

        awarded = check_and_award_badges(current_user) or []
        return jsonify({'success': True, 'awarded': awarded})

    return jsonify({'success': False, 'error': 'Invalid passcode'})


# ✅ Edit Event
@events.route('/edit-event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.creator_id != current_user.id:
        flash('❌ Not authorized to edit this event.', 'danger')
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        event.title = request.form['title']
        event.description = request.form['description']
        event.location = request.form['location']
        event.latitude = float(request.form.get('latitude') or 0)
        event.longitude = float(request.form.get('longitude') or 0)
        event.passcode = request.form.get('passcode')

        try:
            event.date = datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('❌ Invalid date format.', 'danger')
            return redirect(url_for('events.edit_event', event_id=event.id))

        thumbnail = request.files.get('thumbnail')
        if thumbnail and thumbnail.filename:
            filename = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            event.thumbnail = filename

        db.session.commit()
        flash('✅ Event updated successfully!', 'success')
        return redirect(url_for('events.manage_events'))

    return render_template('edit_event.html', event=event)

@events.route('/delete-event/<int:event_id>', methods=['POST'])
@login_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.creator_id != current_user.id and not current_user.is_admin:
        flash("❌ You are not authorized to delete this event.", "danger")
        return redirect(url_for('events.manage_events'))

    # Delete related records
    AttendanceRecord.query.filter_by(event_id=event.id).delete()
    Booking.query.filter_by(event_id=event.id).delete()
    db.session.delete(event)
    db.session.commit()

    flash("✅ Event deleted.", "success")
    return redirect(url_for('events.manage_events'))

@events.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    ids = request.form.getlist('delete_ids')
    deleted_count = 0

    for event_id in ids:
        event = Event.query.get(event_id)
        if event and event.creator_id == current_user.id:
            AttendanceRecord.query.filter_by(event_id=event.id).delete()
            Booking.query.filter_by(event_id=event.id).delete()
            db.session.delete(event)
            deleted_count += 1

    db.session.commit()
    flash(f"✅ {deleted_count} event(s) deleted.", "success")
    return redirect(url_for('events.manage_events'))


# ✅ Preview QR and Passcode
@events.route('/event/<int:event_id>/preview', methods=['GET'])
@login_required
def preview_qr_passcode(event_id):
    event = Event.query.get_or_404(event_id)

    if event.creator_id != current_user.id:
        flash("You are not authorized to view this QR code.", "danger")
        return redirect(url_for('dashboard.home'))

    return render_template('preview_qr.html', event=event)

# ✅ Bulk Create Events from CSV
@events.route('/bulk-create', methods=['POST'])
@login_required
def bulk_create():
    file = request.files.get('bulk_file')
    if not file or not file.filename.endswith('.csv'):
        flash("❌ Please upload a valid CSV file.", "danger")
        return redirect(url_for('events.create_event'))

    import csv
    import io

    csv_data = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(csv_data)
    created_count = 0

    for row in reader:
        try:
            title = row['title']
            date = datetime.strptime(row['date'], '%Y-%m-%dT%H:%M')
            duration = int(row.get('duration', 1))
            xp_score = int(row.get('xp_score', 10))
            location = row['location']
            latitude = float(row['latitude'])
            longitude = float(row['longitude'])
            passcode = row.get('passcode', '')
            category = row.get('category', 'Cleanup')
            tags = row.get('tags', '')
            description = row.get('description', '')

            event = Event(
                title=title,
                date=date,
                duration=duration,
                xp_score=xp_score,
                location=location,
                latitude=latitude,
                longitude=longitude,
                passcode=passcode,
                category=category,
                tags=tags,
                description=description,
                creator_id=current_user.id
            )
            db.session.add(event)
            created_count += 1
        except Exception as e:
            print("Error in row:", row, e)
            continue

    db.session.commit()
    flash(f"✅ {created_count} event(s) uploaded successfully!", "success")
    return redirect(url_for('events.manage_events'))


# View to render the duplicate event page
@events.route('/duplicate-event')
@login_required
def duplicate_event():
    upcoming_events = Event.query.filter(Event.creator_id == current_user.id, Event.date >= datetime.now()).all()
    return render_template('duplicate_event.html', upcoming_events=upcoming_events)

from flask import Blueprint, request, jsonify
from app import db
from app.models import Event  # Make sure this is correct



@events.route("/api/duplicate-event/<int:event_id>", methods=["POST"], endpoint='duplicate_event_api')
def duplicate_event_api(event_id):

    original = Event.query.get(event_id)
    if not original:
        return jsonify({"error": "Event not found"}), 404

    data = request.get_json()
    new_title = data.get("title")
    new_date = data.get("date")
    new_location = data.get("location", "EcoNova Venue")

    try:
        new_event = Event(
            title=new_title or original.title,
            date=datetime.strptime(new_date, "%Y-%m-%d").date(),
            location=new_location,
            thumbnail=original.thumbnail,
        )
        db.session.add(new_event)
        db.session.commit()
        return jsonify({"message": "Event duplicated successfully", "new_id": new_event.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



@events.route('/feedback-summary')
@login_required
def feedback_summary():
    return render_template('feedback_summary.html')

# ✅ View Event Details
@events.route('/view-event/<int:event_id>', endpoint='view_event')
@login_required
def view_event(event_id):
    event = Event.query.get_or_404(event_id)
    booking = Booking.query.filter_by(user_id=current_user.id, event_id=event_id).first()
    return render_template('view_event.html', event=event, booking=booking)

from app.models import User, Notification
from app import db, socketio
from geopy.distance import geodesic

def notify_nearby_volunteers(event):
    event_location = (event.latitude, event.longitude)

    volunteers = User.query.filter_by(role='volunteer').all()

    for volunteer in volunteers:
        if volunteer.latitude and volunteer.longitude:
            user_location = (volunteer.latitude, volunteer.longitude)
            distance = geodesic(event_location, user_location).km
            print(f"Checking distance for {volunteer.name}: {distance}km")

            if distance <= 10:
                # Create notification
                notification = Notification(
                    user_id=volunteer.id,
                    title=f"New Event Near You: {event.name}",
                    message=f"{event.name} is happening on {event.date.strftime('%d %b %Y')}",
                    icon="geo-alt-fill"
                )
                db.session.add(notification)
                db.session.commit()

                # Emit to personal room
                socketio.emit('new_notification', {
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'timestamp': notification.timestamp.strftime('%d %b %Y'),
                    'icon': notification.icon
                }, room=f"user_{volunteer.id}")
