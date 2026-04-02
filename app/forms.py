from flask_wtf import FlaskForm
from wtforms import StringField, FileField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email

class EditProfileForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    bio = TextAreaField("Bio")
    location = StringField("Location")
    instagram = StringField("Instagram Handle")
    profile_pic = FileField("Update Profile Picture")


from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, FileField
from wtforms.validators import DataRequired, Optional

class BadgeForm(FlaskForm):
    name = StringField('Badge Name', validators=[DataRequired()])
    description = TextAreaField('Description')
    image_file = FileField('Badge Icon')
    level = SelectField('Level', choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('pro', 'Pro')])
    tags = StringField('Tags')
    xp_reward = IntegerField('XP Reward')
    condition_type = SelectField('Condition Type', choices=[
    ('event_attendance', 'Attend X Events'),
    ('event_host', 'Host X Events'),
    ('checkins', 'Check-in X Times'),
    ('hours_volunteered', 'Volunteer for X Hours'),
    ('weekly_goals_met', 'Achieve Weekly Goals X Times'),
    ('xp_earned', 'Earn X XP'),
    ('level_reached', 'Reach Level X'),
    ('badges_collected', 'Collect X Badges'),
    ('certificates_earned', 'Earn X Certificates'),
])

    condition_value = IntegerField('Condition Value', validators=[DataRequired()])
    submit = SubmitField('Create Badge')


