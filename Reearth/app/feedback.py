from flask import Blueprint
from flask_socketio import emit
from flask_login import current_user
from app import socketio, db
from app.models import Feedback
from sqlalchemy.sql import func
import datetime

feedback_bp = Blueprint("feedback", __name__)

@socketio.on("connect")
def send_feedback_data():
    if not current_user.is_authenticated:
        return

    # --- Feedback Stats
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar() or 0
    total_responses = Feedback.query.count()
    positive_count = Feedback.query.filter(Feedback.rating >= 4).count()
    positive_percent = round((positive_count / total_responses) * 100, 1) if total_responses else 0

    emit("feedback_stats", {
        "avg_rating": round(avg_rating, 2),
        "total_responses": total_responses,
        "positive_percent": positive_percent
    })

    # --- Rating Breakdown
    breakdown = {}
    for i in range(1, 6):
        votes = Feedback.query.filter_by(rating=i).count()
        breakdown[i] = round((votes / total_responses) * 100, 1) if total_responses else 0
        breakdown[f"{i}_votes"] = votes

    emit("rating_breakdown", breakdown)

    # --- Common Keywords
    all_feedback = Feedback.query.with_entities(Feedback.comment).all()
    keyword_counts = {}
    for row in all_feedback:
        if row.comment:
            for word in row.comment.lower().split():
                if len(word) > 3:
                    keyword_counts[word] = keyword_counts.get(word, 0) + 1
    sorted_keywords = sorted(keyword_counts, key=keyword_counts.get, reverse=True)[:12]
    emit("feedback_keywords", sorted_keywords)

    # --- Trend Chart Data
    last_10_days = db.session.query(
        func.date(Feedback.timestamp),
        func.avg(Feedback.rating)
    ).group_by(func.date(Feedback.timestamp))\
     .order_by(func.date(Feedback.timestamp).desc())\
     .limit(10).all()

    labels = [d[0].strftime("%b %d") for d in reversed(last_10_days)]
    values = [round(d[1], 2) for d in reversed(last_10_days)]
    emit("trend_data", {"labels": labels, "values": values})
