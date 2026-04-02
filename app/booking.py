from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from .models import Event, Booking
from . import db

bookings = Blueprint('bookings', __name__)

@bookings.route('/my-bookings')
@login_required
def my_bookings():
    user_bookings = Booking.query.filter_by(user_id=current_user.id).all()

    # Ensure event.date is datetime (not string)
    for booking in user_bookings:
        if isinstance(booking.event.date, str):
            try:
                booking.event.date = datetime.strptime(booking.event.date, "%Y-%m-%d")
            except ValueError:
                booking.event.date = datetime.now()

    return render_template('bookings.html', user=current_user, bookings=user_bookings)


@bookings.route('/cancel-booking/<int:booking_id>')
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('bookings.my_bookings'))

    db.session.delete(booking)
    db.session.commit()
    flash('Booking cancelled successfully.', 'success')

    return redirect(url_for('bookings.my_bookings'))


@bookings.route('/edit-booking/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def edit_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash('Unauthorized access to edit.', 'danger')
        return redirect(url_for('bookings.my_bookings'))

    if request.method == 'POST':
        new_notes = request.form.get('notes')
        booking.notes = new_notes
        db.session.commit()
        flash('Booking updated successfully.', 'success')
        return redirect(url_for('bookings.my_bookings'))

    return render_template('edit_booking.html', booking=booking, event=booking.event)
