import os
import json
from flask import Flask, request, render_template, jsonify, flash, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import google.generativeai as genai
from flask_migrate import Migrate
from pypdf import PdfReader
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import docx
from redis import Redis
import rq
import stripe
# --- 1. INITIALIZE EXTENSIONS (but don't connect to an app yet) ---
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


# --- 2. HELPER & AI FUNCTIONS ---
from io import BytesIO

def extract_text_from_file(file_obj, filename):
    """Extracts text from PDF or DOCX file-like objects."""
    if filename.endswith('.pdf'):
        # PdfReader can take a file-like object directly
        reader = PdfReader(file_obj)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    elif filename.endswith('.docx'):
        # docx needs a stream/BytesIO object
        # werkzeug FileStorage objects are already streams, but wrapping it
        # ensures compatibility with python-docx
        file_stream = BytesIO(file_obj.read())
        doc = docx.Document(file_stream)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    else:
        raise ValueError("Unsupported file type.")

# AI functions moved to tasks.py

# --- 3. DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    subscription_tier = db.Column(db.String(20), default='standard', nullable=False)
    uploads_today = db.Column(db.Integer, default=0)  # ADD THIS LINE
    last_upload_date = db.Column(db.Date, default=datetime.utcnow().date())
    job_postings = db.relationship('JobPosting', backref='user', lazy=True, cascade="all, delete-orphan")

class JobPosting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    positions_to_fill = db.Column(db.Integer, nullable=False, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    candidates = db.relationship('Candidate', backref='job_posting', lazy=True, cascade="all, delete-orphan")

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    extracted_text = db.Column(db.Text, nullable=False)
    match_score = db.Column(db.Integer, default=0)
    match_reasoning = db.Column(db.Text, nullable=True)
    job_posting_id = db.Column(db.Integer, db.ForeignKey('job_posting.id'), nullable=False)


# --- 4. THE APPLICATION FACTORY ---
def create_app():
    app = Flask(__name__)

    # --- App Configuration ---
    app.config['UPLOAD_FOLDER'] = 'uploads'
    database_url = os.environ.get("DATABASE_URL", 'postgresql://ai_resume:ai_resume@localhost:5432/postgres')
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", 'default_secret_key')
    app.config['STRIPE_SECRET_KEY'] = os.environ.get("STRIPE_SECRET_KEY")
    app.config['STRIPE_PRICE_ID_PRO_MONTHLY'] = 'price_1S65g8GrAII97171sHuP11Us'
    app.config['STRIPE_PRICE_ID_PREMIUM_YEARLY'] = 'price_1S65g9GrAII97171AHehkFtw'
    app.config['REDIS_URL'] = os.environ.get('REDIS_URL') or 'redis://localhost:6379'
    
    # --- Connect Extensions to the App ---
    db.init_app(app)
    migrate.init_app(app, db)
    stripe.api_key = app.config['STRIPE_SECRET_KEY']
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # --- Initialize Redis Queue (needs app.config) ---
    app.redis_conn = Redis.from_url(app.config['REDIS_URL'])
    app.q = rq.Queue('resume-analyzer', connection=app.redis_conn)
    
    # --- Define Routes within the Factory ---
    with app.app_context():
        # User loader for Flask-Login
        @login_manager.user_loader
        def load_user(user_id):
            return db.session.get(User, int(user_id))

        # All other routes
        @app.route('/app')
        def index():
            return render_template('index.html')
        # In app.py
        @app.route('/')
        def landing():
            # Now, this route will always show the landing page
            return render_template('landing.html')

        @app.route('/register', methods=['GET', 'POST'])
        def register():
            # ... (your register logic here) ...
            if request.method == 'POST':
                # ...
                new_user = User(username=request.form.get('username'), password=generate_password_hash(request.form.get('password'), method='pbkdf2:sha256'))
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                return redirect(url_for('dashboard'))
            return render_template('register.html')

        @app.route('/login', methods=['GET', 'POST'])
        def login():
            # ... (your login logic here) ...
             if request.method == 'POST':
                user = User.query.filter_by(username=request.form.get('username')).first()
                if user and check_password_hash(user.password, request.form.get('password')):
                    login_user(user)
                    return redirect(url_for('dashboard'))
                flash('Please check your login details and try again.')
             return render_template('login.html')

        @app.route('/logout')
        @login_required
        def logout():
            logout_user()
            return redirect(url_for('index'))

        @app.route('/upload', methods=['POST'])
        @login_required
        def upload_file():
            files = request.files.getlist('files')
            
            # --- PLAN RESTRICTION CHECK ---
            if current_user.subscription_tier == 'standard':
                today = datetime.utcnow().date()
                
                # If it's a new day, reset the user's daily count
                if current_user.last_upload_date != today:
                    current_user.last_upload_date = today
                    current_user.uploads_today = 0
                    # The commit will happen later, after the main logic

                # Check if this upload would exceed the daily limit of 5
                limit = 5
                if (current_user.uploads_today + len(files)) > limit:
                    remaining = limit - current_user.uploads_today
                    error_message = f"Your standard plan is limited to {limit} uploads per day. You have {remaining} uploads remaining."
                    return jsonify({"error": error_message}), 429 # 429: Too Many Requests

            # --- If the check passes, or if the user is Pro/Premium, proceed ---
            job_description = request.form.get('job-description')
            positions_to_fill = request.form.get('positions', 1, type=int)

            if not job_description or not files:
                return jsonify({"error": "Job description and resume files are required."}), 400

            try:
                new_job_posting = JobPosting(
                    job_description=job_description,
                    user_id=current_user.id,
                    positions_to_fill=positions_to_fill
                )
                db.session.add(new_job_posting)
                
                # After a successful job posting, update the user's upload count if they are on the standard plan
                if current_user.subscription_tier == 'standard':
                    current_user.uploads_today += len(files)
                
                db.session.commit() # Commit the new JobPosting and the updated user count

                # Create Candidate records
                for file in files:
                    if file and file.filename != '':
                        extracted_text = extract_text_from_file(file, file.filename)
                        new_candidate = Candidate(
                            original_filename=file.filename,
                            extracted_text=extracted_text,
                            job_posting_id=new_job_posting.id
                        )
                        db.session.add(new_candidate)
                
                db.session.commit() # Commit the new candidates

                # Enqueue jobs for the background worker
                from tasks import run_ai_analysis
                for candidate in new_job_posting.candidates:
                    app.q.enqueue(run_ai_analysis, candidate.id)
                    
                return jsonify({
                    "message": f"Your {len(new_job_posting.candidates)} resumes have been submitted for analysis.",
                    "job_posting_id": new_job_posting.id
                })
            except Exception as e:
                db.session.rollback()
                return jsonify({"error": str(e)}), 500
        
        # In app.py, replace the old checkout and success routes
        @app.route('/create-checkout-session/<plan>')
        @login_required
        def create_checkout_session(plan):
            # Look up the Price ID from our config based on the plan
            price_id = None
            if plan == 'pro':
                price_id = app.config['STRIPE_PRICE_ID_PRO_MONTHLY']
            elif plan == 'premium':
                price_id = app.config['STRIPE_PRICE_ID_PREMIUM_YEARLY']
            
            if not price_id:
                return "Invalid plan selected", 400

            try:
                checkout_session = stripe.checkout.Session.create(
                    line_items=[{'price': price_id, 'quantity': 1}],
                    mode='subscription',
                    # Pass the plan name to the success page
                    success_url=url_for('success', plan=plan, _external=True),
                    cancel_url=url_for('cancel', _external=True),
                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                return str(e)

        @app.route('/success')
        @login_required # Protect this route
        def success():
            # Get the plan from the URL query parameter
            plan = request.args.get('plan')
            
            if plan in ['pro', 'premium']:
                current_user.subscription_tier = plan
                db.session.commit()
                flash(f"Payment successful! You are now on the {plan.capitalize()} plan.")
            else:
                flash("An unexpected error occurred during subscription update.")
                
            return redirect(url_for('dashboard'))

        @app.route('/cancel')
        def cancel():
            flash("Payment was cancelled.")
            return redirect(url_for('index'))
        
        # In app.py, inside the with app.app_context(): block

        @app.route('/dashboard')
        @login_required
        def dashboard():
            # Get all job postings for the current user, newest first
            postings = JobPosting.query.filter_by(user_id=current_user.id).order_by(JobPosting.created_at.desc()).all()
            return render_template('dashboard.html', postings=postings)


        @app.route('/job/<int:job_id>')
        @login_required
        def job_results(job_id):
            # This route just renders the page. JavaScript will fetch the data.
            job = db.session.get(JobPosting, job_id)
            # Ensure the user can only see their own jobs
            if job is None or job.user_id != current_user.id:
                flash("Job posting not found or you do not have permission to view it.")
                return redirect(url_for('dashboard'))
            return render_template('job_results.html', job=job)


        @app.route('/api/job/<int:job_id>/results')
        @login_required
        def api_job_results(job_id):
            # This route provides the data as JSON
            job = db.session.get(JobPosting, job_id)
            if job is None or job.user_id != current_user.id:
                return jsonify({"error": "Not authorized"}), 403

            # Get candidates and rank them by score, highest first
            candidates = Candidate.query.filter_by(job_posting_id=job_id).order_by(Candidate.match_score.desc()).all()
            
            # Convert candidate objects to a list of dictionaries
            results = [{
                'id': c.id,
                'filename': c.original_filename,
                'score': c.match_score,
                'reasoning': c.match_reasoning
            } for c in candidates]
            
            return jsonify(results)

    return app


# --- 5. WORKER TASK (Needs its own app context) ---
# Moved to tasks.py

# --- 6. MAIN EXECUTION BLOCK (for running the web server) ---
if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True)

# --- Worker Task (This also needs the app context) ---


# --- App Configuration (ALL config goes here, right after creating the app) ---





