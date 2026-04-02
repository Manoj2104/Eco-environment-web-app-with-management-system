# app/task_engine.py
import json

# Category-based task templates
TASK_TEMPLATES = {
    'Cleanup': [
        {"title": "Survey the Area", "description": "Walk around the event area and note all major waste zones.", "xp": 10},
        {"title": "Collect Plastic Waste", "description": "Collect all plastic bottles and bags in your assigned zone.", "xp": 15},
        {"title": "Segregate Waste", "description": "Sort collected waste into plastic, paper, and organic bins.", "xp": 15},
        {"title": "Document Before State", "description": "Upload a photo showing the area before cleanup.", "xp": 10},
        {"title": "Clean Assigned Zone", "description": "Fully clean your assigned zone and upload photo proof.", "xp": 20},
        {"title": "Document After State", "description": "Upload a photo of the cleaned area.", "xp": 15},
        {"title": "Handover to Disposal Team", "description": "Hand collected waste bags to the disposal team and confirm.", "xp": 10},
        {"title": "Final Zone Inspection", "description": "Do a final walkthrough and confirm zone is clean.", "xp": 5},
    ],
    'Tree Plantation': [
        {"title": "Site Survey", "description": "Identify suitable spots for planting trees.", "xp": 10},
        {"title": "Collect Saplings", "description": "Collect your assigned saplings from the distribution point.", "xp": 10},
        {"title": "Dig Planting Holes", "description": "Dig holes as per guidelines and upload photo.", "xp": 15},
        {"title": "Plant the Sapling", "description": "Plant the sapling correctly and upload close-up photo.", "xp": 20},
        {"title": "Water the Plants", "description": "Water all planted saplings and capture proof.", "xp": 15},
        {"title": "Label the Tree", "description": "Place a name tag on your planted tree and photograph.", "xp": 10},
        {"title": "Record GPS Location", "description": "Note down the GPS location of your planted tree.", "xp": 10},
    ],
    'Awareness': [
        {"title": "Set Up Stall", "description": "Set up your awareness stall and upload a photo.", "xp": 10},
        {"title": "Distribute Pamphlets", "description": "Distribute eco awareness pamphlets and log count.", "xp": 15},
        {"title": "Engage 5 People", "description": "Talk to at least 5 people about the cause and document.", "xp": 20},
        {"title": "Collect Pledges", "description": "Get at least 3 people to sign the eco pledge.", "xp": 20},
        {"title": "Social Media Post", "description": "Post about the event on social media and share link.", "xp": 15},
        {"title": "Wrap Up Stall", "description": "Clean and pack the stall area neatly.", "xp": 10},
    ],
    'Waste Management': [
        {"title": "Map Waste Points", "description": "Identify all waste collection points in the area.", "xp": 10},
        {"title": "Setup Bins", "description": "Place segregation bins at assigned spots.", "xp": 15},
        {"title": "Monitor Collection", "description": "Monitor bins and ensure correct waste segregation.", "xp": 15},
        {"title": "Compost Organic Waste", "description": "Transfer organic waste to composting area.", "xp": 20},
        {"title": "Record Waste Volume", "description": "Estimate and log the volume of waste collected.", "xp": 15},
        {"title": "Final Report Photo", "description": "Upload a photo of the filled waste collection area.", "xp": 15},
    ]
}

TASK_QUESTIONS = {
    'Cleanup': [
        {"question": "What type of waste is most commonly found in beach cleanups?", "options": ["Plastic", "Glass", "Metal", "Paper"], "correct": "Plastic"},
        {"question": "Which bin should you put plastic bottles in?", "options": ["Blue (Plastic)", "Green (Organic)", "Red (Hazardous)", "Yellow (Paper)"], "correct": "Blue (Plastic)"},
        {"question": "What should you wear during cleanup for safety?", "options": ["Gloves and mask", "Just gloves", "Nothing needed", "Sunglasses only"], "correct": "Gloves and mask"},
    ],
    'Tree Plantation': [
        {"question": "How deep should a planting hole be for a small sapling?", "options": ["Twice the root ball depth", "1 inch deep", "Same as pot size", "10 feet deep"], "correct": "Twice the root ball depth"},
        {"question": "How often should a newly planted tree be watered?", "options": ["Daily for first 2 weeks", "Once a month", "Never", "Only when it rains"], "correct": "Daily for first 2 weeks"},
        {"question": "What is the best time to plant a tree?", "options": ["Early morning", "Afternoon", "Midnight", "During rain"], "correct": "Early morning"},
    ],
    'Awareness': [
        {"question": "What is the 3R principle in environmental awareness?", "options": ["Reduce, Reuse, Recycle", "Remove, Replace, Restore", "Read, Run, Record", "Repair, Rebuild, Renew"], "correct": "Reduce, Reuse, Recycle"},
        {"question": "Which gas is primarily responsible for global warming?", "options": ["CO2", "O2", "N2", "H2"], "correct": "CO2"},
    ],
    'Waste Management': [
        {"question": "What color bin is used for dry waste in India?", "options": ["Blue", "Green", "Red", "Yellow"], "correct": "Blue"},
        {"question": "What is composting?", "options": ["Breaking organic waste into fertilizer", "Burning plastic", "Recycling metals", "Filtering water"], "correct": "Breaking organic waste into fertilizer"},
    ]
}

def generate_tasks_for_event(event, db, Task, TaskQuestion):
    """Auto-generate 5-8 tasks based on event category."""
    category = event.category or 'Cleanup'
    templates = TASK_TEMPLATES.get(category, TASK_TEMPLATES['Cleanup'])
    questions_pool = TASK_QUESTIONS.get(category, TASK_QUESTIONS['Cleanup'])

    import random
    count = random.randint(5, min(8, len(templates)))
    selected = random.sample(templates, count)

    for i, t in enumerate(selected, start=1):
        task = Task(
            event_id=event.id,
            title=t['title'],
            description=t['description'],
            order=i,
            xp_reward=t['xp']
        )
        db.session.add(task)
        db.session.flush()  # get task.id

        # Add 1-2 questions per task
        q_sample = random.sample(questions_pool, min(2, len(questions_pool)))
        for q in q_sample:
            question = TaskQuestion(
                task_id=task.id,
                question=q['question'],
                options=json.dumps(q['options']),
                correct_answer=q['correct'],
                question_type='mcq'
            )
            db.session.add(question)

    db.session.commit()