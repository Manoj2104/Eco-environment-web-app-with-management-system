# utils/archive.py
from datetime import datetime, timedelta
from app.models import Event, db

def archive_past_events():
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=45)

    outdated_events = Event.query.filter(Event.date < cutoff, Event.archived == False).all()

    for event in outdated_events:
        event.archived = True
    db.session.commit()
