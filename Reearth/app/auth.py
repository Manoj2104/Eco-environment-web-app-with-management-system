# app/auth.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from . import db, login_manager
from .models import User

auth = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', category='success')
            
            # 🔁 Redirect based on role
            if user.role == 'host':
                return redirect(url_for('events.create_event'))
            else:
                return redirect(url_for('dashboard.home'))
        else:
            flash('Invalid credentials', category='error')
            return render_template('login_register.html', show_register=False)

    return render_template('login_register.html', show_register=False)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'volunteer') 
        gender = request.form.get('gender')

        if User.query.filter_by(email=email).first():
            flash('Email is already registered', category='error')
            return render_template('login_register.html', show_register=True)

        new_user = User(
            name=name,
            email=email,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            role=role  # ✅ Save host/volunteer role
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully. Please log in.', category='success')
        return redirect(url_for('auth.login'))

    return render_template('login_register.html', show_register=True)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', category='info')
    return redirect(url_for('main.home'))
