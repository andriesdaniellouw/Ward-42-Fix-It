# IMPORTS
import os
import re
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps

import click
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# SECRET KEY
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fixit.db"

app.config["SQLALCHEMY_ECHO"] = os.environ.get("WARD42_SQL_ECHO") == "1"

# PHOTOS
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")

# MAX LENGTH
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024

# COOKIES
IS_PRODUCTION = os.environ.get("WARD42_ENV") == "production"

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

# MAX PHOTO SIZE
MAX_PHOTO_BYTES = 2 * 1024 * 1024
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# DATABASE
db = SQLAlchemy(app)

# CSRF
csrf = CSRFProtect(app)

CATEGORIES = ["Water leak", "Pothole", "Streetlight", "Dumping", "other"]
STATUSES = ["Open", "In Progress", "Closed"]

# DATABASE MODEL
# REPORT CLASS
class Report(db.Model):
    __tablename__ = "reports"

    # INTERNAL KEY
    id = db.Column(db.Integer, primary_key=True)

    # PUBLIC REFERENCE NUMBER
    reference = db.Column(db.String(20), unique=True, nullable=False)

    # CATEGORY, STREET, DESCRIPTION
    category = db.Column(db.String(50), nullable=False)
    street = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=False)

    # PHOTO FILE NAME
    photo = db.Column(db.String(100), nullable=True)

    # RESIDENTS INFO
    resident_name = db.Column(db.String(100), nullable=False)
    cell = db.Column(db.String(20), nullable=False)
    consent = db.Column(db.Boolean, nullable=False, default=False)

    # STATUS
    status = db.Column(db.String(20), nullable=False, default="Open")
    
    # CREATED AND UPDATED DATES
    created = db.Column(db.DateTime, nullable=False, default= lambda: datetime.now(timezone.utc))
    updated = db.Column(db.DateTime, nullable=False, default = lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
# REF NUM
REF_NUM = "0123456789"
    
# REFERENCE GENERATOR FUNCTION
def generate_reference():
    return "W42-" + "".join(secrets.choice(REF_NUM) for _ in range(6))

# CREATE REPORT FUNCTION
def create_report(**fields):
    
    for _ in range(5):
        report = Report(reference = generate_reference(), **fields)
        db.session.add(report)
        
        try:
            db.session.commit()
            return report
        except IntegrityError as error:
            db.session.rollback()
            
            if "reports.reference" not in str(error.orig):
                raise
    
    raise RuntimeError("Could not generate a unique reference number")

# COORDINATOR CLASS
class Coordinator (db.Model):
    __tablename__ = "coordinators"
    
    # INTERNAL KEY
    id = db.Column(db.Integer, primary_key=True)
    
    # USERNAME AND PASSWORD
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(225), nullable=False)
    
    # SET PASSWORD FUNCTION
    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    
    # CHECK PASSWORD FUNCTION
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
# CREATE COORDINATOR FUNCTION
def create_coordinator(username, password):
    coordinator = Coordinator(username=username)
    coordinator.set_password(password)
    
    db.session.add(coordinator)
    db.session.commit()
    return coordinator

# LOG IN REQUIRED FUNCTION
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("coordinator"):
            flash("Please log in to use that page", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

# LOG IN FUNCTION
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
 
        if not username or len(username) > 50 or not password or len(password) > 128:
            flash("Please enter a valid username and password.", "danger")
            return render_template("login.html"), 400
 
        user = Coordinator.query.filter_by(username=username).first()
 
        if user and user.check_password(password):
            session.clear()  
            session["coordinator"] = True
            session.permanent = True 
            flash("You are logged in.", "success")
            return redirect(url_for("reports"))
 
        flash("Incorrect username or password.", "danger")
        return render_template("login.html"), 401
 
    return render_template("login.html")


# LOG OUT FUNCTION
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Successfully logged out")
    return redirect(url_for("index"))

# PATTERNs
CELL_PATTERN = re.compile(r"^\+?[0-9 ]{10,15}$")

REF_PATTERN = re.compile(r"^W42-[0-9]{6}$")

PHOTO_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")

UNSAFE_TEXT = re.compile(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f]")

# SAVE PHOTO FUNCTION
def save_photo(file):
   
    if not file or not file.filename:
        return None 
 
    start = file.read(8)
    file.seek(0)
    if start.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    elif start.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    else:
        raise ValueError("The photo must be a JPG or PNG image")
 
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_PHOTO_BYTES:
        raise ValueError("The photo may not be larger than 2 MB. Please choose a smaller photo")
 
    filename = uuid.uuid4().hex + extension
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename

# INDEX
@app.route("/")
def index():
    return render_template("index.html")

# CREATE REPORT
@app.route("/report", methods=["GET", "POST"])
def report():
    
    if request.method == "POST":
        
        category = request.form.get("category", "")
        street = request.form.get("street", "").strip()
        description = request.form.get("description", "").strip()
        resident_name = request.form.get("resident_name", "").strip()
        cell = request.form.get("cell", "").strip()
        consent = request.form.get("consent") == "yes"
 
        # SERVER VALIDATION
        errors = []
        if category not in CATEGORIES:
            errors.append("Please choose a category from the list")
        if not street or len(street) > 100:
            errors.append("Please enter the street name (up to 100 characters)")
        if len(description) < 10 or len(description) > 500:
            errors.append("Please describe the fault in 10 to 500 characters")
        if not resident_name or len(resident_name) > 100:
            errors.append("Please enter your name.")
        if any(UNSAFE_TEXT.search(text) for text in (street, description, resident_name)):
            errors.append("Please do not use the < or > symbols in your answers")
        if not CELL_PATTERN.match(cell):
            errors.append("Please enter a valid cell phone number")
        if not consent:
            errors.append("Please tick the box to agree that we may contact you about this report")
 
        photo_name = None
        if not errors:
            try:
                photo_name = save_photo(request.files.get("photo"))
            except ValueError as problem:
                errors.append(str(problem))
 
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template("report.html", categories=CATEGORIES), 400
 
        try:
            # CREATE REPORT
            new_report = create_report(
                category=category, street=street, description=description,
                photo=photo_name, resident_name=resident_name, cell=cell, consent=consent,
            )
        except Exception:
            
            if photo_name:
                os.remove(os.path.join(app.config["UPLOAD_FOLDER"], photo_name))
            raise
 
        return redirect(url_for("confirmation", reference=new_report.reference))
 
    return render_template("report.html", categories=CATEGORIES)

# SHOW CONFIRMATION
@app.route("/report/confirmation/<reference>")
def confirmation(reference):
    if not REF_PATTERN.match(reference):
        abort(404)
    report_row = Report.query.filter_by(reference=reference).first_or_404()
    return render_template("confirmation.html", report=report_row)

# CHECK STATUS FUNCTION
@app.route("/status")
def status():
    
    ref = request.args.get("ref", "").strip().upper()
    
    report_row = None
    ref_invalid = False
    if ref and not REF_PATTERN.match(ref):

        ref, ref_invalid = "", True
    elif ref:

        report_row = Report.query.filter_by(reference=ref).first()
    return render_template("status.html", ref=ref, report=report_row, ref_invalid=ref_invalid)

# LIST ALL REPORTS FUNCTION
@app.route("/reports")
@login_required
def reports():

    selected_category = request.args.get("category", "")
    selected_status = request.args.get("status", "")
    
    if selected_category not in CATEGORIES:
        selected_category = ""
        
    if selected_status not in STATUSES:
        selected_status = ""
 
    query = Report.query
    
    if selected_category:
        query = query.filter_by(category=selected_category)
        
    if selected_status:
        query = query.filter_by(status=selected_status)
        
    rows = query.order_by(Report.created.desc()).all()  
 
    return render_template("reports.html", reports=rows, categories=CATEGORIES,
                           statuses=STATUSES, selected_category=selected_category,
                           selected_status=selected_status)
    
# UPDATE REPORT STATUS FUNCTION 
@app.route("/reports/<int:report_id>/status", methods=["POST"])
@login_required
def update_status(report_id):
   
    new_status = request.form.get("status", "")
    
    if new_status not in STATUSES:
        return "Invalid status", 400
 
    row = db.get_or_404(Report, report_id) 
    row.status = new_status
    db.session.commit() 
    
    flash(f"Report {row.reference} is now: {new_status}", "success")
    return redirect(url_for("reports"))

# CHECK PHOTO FUNCTION
@app.route("/photos/<filename>")
@login_required
def photo(filename):
    if not PHOTO_PATTERN.match(filename):
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# SHOW DASHBOARD FUNCTION
@app.route("/dashboard")
@login_required
def dashboard():
   
    rows = (db.session.query(Report.category, Report.status, func.count(Report.id))
            .group_by(Report.category, Report.status).all())
 
    matrix = {c: {s: 0 for s in STATUSES} for c in CATEGORIES}
    by_status = {s: 0 for s in STATUSES}
    for category, status_value, count in rows:
        if category in matrix:
            matrix[category][status_value] = count
        by_status[status_value] += count
 
    return render_template("dashboard.html", statuses=STATUSES, categories=CATEGORIES,
                           by_status=by_status, matrix=matrix)
   
  
# PWA
# OFFLINE PAGE
@app.route("/offline")
def offline():
    return render_template("offline.html")

# SERVICE WORKER
@app.route("/service-worker.js")
def service_worker():
   
    response = send_from_directory(app.root_path, "service-worker.js", mimetype="text/javascript")

    response.headers["Cache-Control"] = "no-cache"
    return response
    
# ERROR HANDLING
# PREVENT LARGE PHOTO UPLOAD FUNCTION
@app.errorhandler(413) 
def too_large(error):
    flash("That upload is too large. Please use a photo under 2 MB.", "danger")
    return redirect(url_for("report"))


CSP = "; ".join([
    "default-src 'self'",                                 
    "script-src 'self' https://cdn.jsdelivr.net",          
    "style-src 'self' https://cdn.jsdelivr.net",         
    "img-src 'self' data:",                               
    "media-src 'self'",                                    
    "connect-src 'self' https://cdn.jsdelivr.net",         
    "object-src 'none'",                                  
    "base-uri 'self'",                                     
    "form-action 'self'",                                 
    "frame-ancestors 'none'",                              
] + (["upgrade-insecure-requests"] if IS_PRODUCTION else []))



# ADD SECURITY HEADERS FUNCTION
@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff" 
    response.headers["X-Frame-Options"] = "DENY"           
    response.headers["Referrer-Policy"] = "same-origin"     

    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


    if session.get("coordinator") and not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


if not IS_PRODUCTION:
    @app.route("/csrf-token")
    def csrf_token_for_tests():
        from flask_wtf.csrf import generate_csrf
        response = jsonify(csrf_token=generate_csrf())
        response.headers["Cache-Control"] = "no-store"
        return response

# RUN IN TERMINAL
@app.cli.command("init-db")
def init_db_command():
    """Create the database file and tables:  flask --app app init-db"""
    db.create_all()
    click.echo("Database ready.")
 
 
@app.cli.command("create-coordinator")
@click.option("--username", prompt=True)
@click.password_option() 
def create_coordinator_command(username, password):
    if len(password) < 10:
        raise click.ClickException("Use a password of at least 10 characters.")
    create_coordinator(username, password)
    click.echo(f"Coordinator '{username}' created.")
 
 
 
if __name__ == "__main__":
    with app.app_context():
        db.create_all() 
    app.run(debug=True)