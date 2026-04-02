from app import create_app, db
from app.models import Event, Feedback, User

app = create_app()

with app.app_context():
    # We want to emulate what /api/feedback-stats does for a host.
    # Current user is host id=... Let's just grab all feedbacks for now for testing
    
    feedbacks = Feedback.query.all()
    
    # 1. basic stats
    total_responses = len(feedbacks)
    avg_rating = sum(f.rating for f in feedbacks) / total_responses if total_responses else 0
    
    # Sentiments: >=4 positive, ==3 neutral, <=2 negative
    positive = sum(1 for f in feedbacks if f.rating >= 4)
    negative = sum(1 for f in feedbacks if f.rating <= 2)
    
    positive_percent = round((positive / total_responses * 100)) if total_responses else 0
    negative_percent = round((negative / total_responses * 100)) if total_responses else 0
    
    # Events count
    events_with_fb = len(set(f.event_id for f in feedbacks))
    
    print(f"Stats: avg={avg_rating}, total={total_responses}, pos%={positive_percent}, neg%={negative_percent}, events={events_with_fb}")
    
    # 2. breakdown 
    # {"1": int, "2": int, "event_count_1": count, "event_1_label": "title"}
    breakdown = {str(i): 0 for i in range(1, 6)}
    
    event_counts = {}
    for f in feedbacks:
        breakdown[str(f.rating)] += 1
        
        if f.event_id not in event_counts:
            # fetch event title
            ev = Event.query.get(f.event_id)
            event_counts[f.event_id] = {"count": 0, "title": ev.title if ev else "Unknown"}
        event_counts[f.event_id]["count"] += 1
        
    for idx, (eid, data) in enumerate(event_counts.items(), 1):
        breakdown[f"event_count_{idx}"] = data["count"]
        breakdown[f"event_{idx}_label"] = data["title"]
        
    print("Breakdown:", breakdown)
    
    # 3. keywords
    # Just a simple top 10 words splitting comment by space
    from collections import Counter
    import re
    words = []
    stopwords = {"and","the","a","is","in","to","of","it","was","for","on","with","as","i","this","that","are","at","be","have","we","you","not","but","very","really","so"}
    for f in feedbacks:
        if f.comment:
            clean = re.sub(r'[^a-zA-Z\s]', '', f.comment).lower()
            words.extend([w for w in clean.split() if w and len(w) > 2 and w not in stopwords])
            
    top_words = [w[0] for w in Counter(words).most_common(12)]
    print("Keywords:", top_words)
    
    # 4. trend (group by day)
    from datetime import timedelta
    trend_dict = {}
    for f in feedbacks:
        date_str = f.timestamp.strftime("%Y-%m-%d") if f.timestamp else "Unknown"
        if date_str not in trend_dict:
            trend_dict[date_str] = []
        trend_dict[date_str].append(f.rating)
        
    # Sort dates and calc average
    sorted_dates = sorted(trend_dict.keys())
    trend = {
        "labels": [d[-5:] for d in sorted_dates], # Just MM-DD
        "values": [round(sum(trend_dict[d])/len(trend_dict[d]), 1) for d in sorted_dates]
    }
    print("Trend:", trend)
    
    # 5. feedbacks list
    fb_list = []
    for f in feedbacks:
        ev = Event.query.get(f.event_id)
        u = User.query.get(f.user_id)
        # Javascript expects: comment, rating, event_title, user_name, timestamp
        fb_list.append({
            "comment": f.comment,
            "rating": f.rating,
            "event_title": ev.title if ev else "Unknown",
            "user_name": u.name if u else "Anonymous",
            "timestamp": f.timestamp.isoformat() if f.timestamp else None
        })
        
    print("\nResult JSON structure ready!")
