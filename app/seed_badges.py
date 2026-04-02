# ══════════════════════════════════════════════════════════════
# STEP 1: Run this once to seed default badges into your DB
# Save as seed_badges.py in your project root, then run:
#   python seed_badges.py
# ══════════════════════════════════════════════════════════════

from app import create_app, db
from app.models import Badge

app = create_app()

DEFAULT_BADGES = [
    {
        'name': 'First Step',
        'description': 'Attended your first eco event.',
        'level': 'Bronze',
        'image_url': '/static/badges/first_step.png',
        'condition_type': 'event_attendance',
        'condition_value': 1,
        'xp_reward': 10,
        'tags': 'beginner,attendance'
    },
    {
        'name': 'Green Warrior',
        'description': 'Attended 3 eco events.',
        'level': 'Silver',
        'image_url': '/static/badges/green_warrior.png',
        'condition_type': 'event_attendance',
        'condition_value': 3,
        'xp_reward': 25,
        'tags': 'attendance,warrior'
    },
    {
        'name': 'Eco Champion',
        'description': 'Attended 5 eco events.',
        'level': 'Gold',
        'image_url': '/static/badges/eco_champion.png',
        'condition_type': 'event_attendance',
        'condition_value': 5,
        'xp_reward': 50,
        'tags': 'champion,attendance'
    },
    {
        'name': 'Task Master',
        'description': 'Completed tasks in 3 events.',
        'level': 'Silver',
        'image_url': '/static/badges/task_master.png',
        'condition_type': 'task_completed',
        'condition_value': 3,
        'xp_reward': 30,
        'tags': 'tasks,master'
    },
    {
        'name': 'XP Hunter',
        'description': 'Earned 100 XP total.',
        'level': 'Gold',
        'image_url': '/static/badges/xp_hunter.png',
        'condition_type': 'xp',
        'condition_value': 100,
        'xp_reward': 20,
        'tags': 'xp,hunter'
    },
    {
        'name': 'Check-In Pro',
        'description': 'Checked in to 5 events.',
        'level': 'Silver',
        'image_url': '/static/badges/checkin_pro.png',
        'condition_type': 'checkin',
        'condition_value': 5,
        'xp_reward': 20,
        'tags': 'checkin,pro'
    },
]

with app.app_context():
    added = 0
    for b in DEFAULT_BADGES:
        exists = Badge.query.filter_by(name=b['name']).first()
        if not exists:
            badge = Badge(**b)
            db.session.add(badge)
            added += 1
    db.session.commit()
    print(f"✅ {added} badges seeded successfully!")
    print(f"📊 Total badges in DB: {Badge.query.count()}")