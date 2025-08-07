# app/main.py

from flask import Blueprint, render_template
from flask_login import current_user, login_required, logout_user

main = Blueprint('main', __name__)

@main.route('/')
def home():
    if current_user.is_authenticated:
        return render_template('dashboard.html', user=current_user)  # 👈 Fix: pass 'user'
    return render_template('index.html')
