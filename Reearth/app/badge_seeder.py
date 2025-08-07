# app/badge_seeder.py

from app import create_app, db
from app.models import Badge

app = create_app()

with app.app_context():
    badges = [
        {"name": "Task Novice", "description": "Completed 1 task!", "icon_url": "/static/icons/novice.png"},
        {"name": "Task Achiever", "description": "Completed 5 tasks!", "icon_url": "/static/icons/achiever.png"},
        {"name": "Task Master", "description": "Completed 10 tasks!", "icon_url": "/static/icons/master.png"},
    ]

    for b in badges:
        exists = Badge.query.filter_by(name=b['name']).first()
        if not exists:
            db.session.add(Badge(**b))
    
    db.session.commit()
    print("✅ Badges seeded successfully.")
