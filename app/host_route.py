@events.route('/event/<int:event_id>/attendance', methods=['GET', 'POST'])
@login_required
def mark_attendance(event_id):
    if current_user.role != 'host':
        return "Access Denied", 403

    event = Event.query.get_or_404(event_id)
    bookings = Booking.query.filter_by(event_id=event_id).all()
    volunteers = [b.user for b in bookings]

    if request.method == 'POST':
        selected_ids = request.form.getlist('attended')
        for v in volunteers:
            status = 'present' if str(v.id) in selected_ids else 'absent'
            record = Attendance(event_id=event.id, volunteer_id=v.id, status=status)
            db.session.add(record)
        db.session.commit()
        flash('Attendance marked successfully!', 'success')
        return redirect(url_for('events.manage_events'))

    return render_template('host_attendance.html', event=event, volunteers=volunteers)

import qrcode
import base64

def generate_qr_base64(data):
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{qr_base64}"

