from os import environ
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.models import User
import random
import time
from flask import Flask, request, render_template, session, flash, redirect, url_for, jsonify
from flask_mail import Mail, Message
from celery import Celery

app = Flask(__name__)
app.config['SECRET_KEY'] = environ.get('SECRET_KEY', 'top-secret')

# Flask-Mail configuration
app.config['MAIL_SERVER'] = environ.get('MAIL_SERVER', 'smtp.googlemail.com')
app.config['MAIL_PORT'] = environ.get('MAIL_PORT', 587)
app.config['MAIL_USE_TLS'] = environ.get('MAIL_USE_TLS', True)
app.config['MAIL_USERNAME'] = environ.get('MAIL_USERNAME', 'matolpydev')
app.config['MAIL_PASSWORD'] = environ.get('MAIL_PASSWORD', 'csszpkcslndaiita')
app.config['MAIL_DEFAULT_SENDER'] = environ.get('MAIL_DEFAULT_SENDER', 'matolpydev@gmail.com')

# Celery configuration
app.config['CELERY_BROKER_URL'] = environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

# Initialize extensions
mail = Mail(app)

# Initialize Celery
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_RESULT_BACKEND'])
celery.conf.update(app.config)


# Create list of email users
def get_users() -> list:
    users_data = []
    users_email = []

    engine = create_engine(environ.get("DSN_FLASK",
                                       "postgresql://celery_ht_user:celery_ht_pswd@127.0.0.1:5431/celery_ht_db"))
    Session = sessionmaker(bind=engine)
    session = Session()

    users = session.query(User).all()

    for user in users:
        users_data.append({user.id: [user.name, user.password, user.email, user.creation_time]})
        users_email.append(user.email)
    session.close()

    return users_email


@celery.task
def send_async_email(email_data):
    """Background task to send an email with Flask-Mail."""
    msg = Message(email_data['subject'],
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[email_data['to']])
    msg.body = email_data['body']
    with app.app_context():
        mail.send(msg)


@celery.task(bind=True)
def long_task(self):
    """Background task that runs a long function with progress reports."""
    verb = ['Starting up', 'Booting', 'Repairing', 'Loading', 'Checking']
    adjective = ['master', 'radiant', 'silent', 'harmonic', 'fast']
    noun = ['solar array', 'particle reshaper', 'cosmic ray', 'orbiter', 'bit']
    message = ''
    total = random.randint(10, 50)
    for i in range(total):
        if not message or random.random() < 0.25:
            message = '{0} {1} {2}...'.format(random.choice(verb),
                                              random.choice(adjective),
                                              random.choice(noun))
        self.update_state(state='PROGRESS',
                          meta={'current': i, 'total': total,
                                'status': message})
        time.sleep(1)
    return {'current': 100, 'total': 100, 'status': 'Task completed!'}


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('index.html', email=session.get('email', ''))
    email = request.form['email']
    session['email'] = email

    # send the email
    email_data = {
        'subject': 'Hello from Flask',
        'to': email,
        'body': 'This is a test email sent from a background Celery task.'
    }
    if request.form['submit'] == 'Send':
        # send right away
        send_async_email.delay(email_data)
        flash('Sending email to {0}'.format(email))
    else:
        # send in one minute
        send_async_email.apply_async(args=[email_data], countdown=60)
        flash('An email will be sent to {0} after one minute'.format(email))

    return redirect(url_for('index'))


@app.route('/longtask', methods=['POST'])
def longtask():
    task = long_task.apply_async()
    return jsonify({}), 202, {'Location': url_for('taskstatus', task_id=task.id)}


@app.route('/status/<task_id>')
def taskstatus(task_id):
    task = long_task.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'current': 0,
            'total': 1,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 1),
            'status': task.info.get('status', '')
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'current': 1,
            'total': 1,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)


if __name__ == '__main__':
    app.run(debug=True)
