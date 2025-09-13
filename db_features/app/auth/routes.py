from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.utils.mail import send_email
from app import limiter
from ..db import db
from ..models import User

auth_bp = Blueprint("auth", __name__)

def _dev_send_reset_link(link: str):
    current_app.logger.info("Password reset link: %s", link)
    if current_app.debug:  # only show in dev
        flash(f"DEV: reset link → {link}", "info")

def _make_reset_token(user_id: int) -> str:
    salt = current_app.config.get("SECURITY_PASSWORD_SALT", "dev-salt-change-me")
    return _serializer().dumps({"uid": user_id}, salt=salt)

def _parse_reset_token(token: str, max_age: int):
    salt = current_app.config.get("SECURITY_PASSWORD_SALT", "dev-salt-change-me")
    data = _serializer().loads(token, salt=salt, max_age=max_age)
    return int(data["uid"])

def _safe_next(default_endpoint="game24.play"):
    nxt = request.args.get("next") or request.form.get("next")
    # allow only local relative paths
    if nxt and nxt.startswith("/"):
        return nxt
    return url_for(default_endpoint)

def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

def _make_reset_token(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id}, salt=current_app.config["SECURITY_PASSWORD_SALT"])

def _parse_reset_token(token: str, max_age: int):
    data = _serializer().loads(token, salt=current_app.config["SECURITY_PASSWORD_SALT"], max_age=max_age)
    return int(data["uid"])

def _safe_next(default_endpoint="game24.play"):
    nxt = request.args.get("next") or request.form.get("next")
    if nxt and nxt.startswith("/"):
        return nxt
    return url_for(default_endpoint)

@auth_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("game24.play"))
    return render_template("auth/login.html")

@auth_bp.post("/login")
@limiter.limit("5 per minute")
def login_post():
    ident = (request.form.get("username_or_email") or "").strip().lower()
    password = request.form.get("password") or ""

    # case-insensitive lookup for either username or email
    user = (User.query.filter(func.lower(User.username) == ident).first()
            or User.query.filter(func.lower(User.email) == ident).first())

    if not user or not check_password_hash(user.password_hash, password):
        flash("Invalid username/email or password.", "error")
        return redirect(url_for("auth.login", next=request.args.get("next")))

    login_user(user)
    return redirect(_safe_next())

@auth_bp.get("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("game24.play"))
    return render_template("auth/register.html")

@auth_bp.post("/register")
def register_post():
    username = (request.form.get("username") or "").strip().lower().replace(" ", "")
    email    = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "")

    if not username or not email or not password:
        flash("All fields are required.", "error")
        return redirect(url_for("auth.register", next=request.args.get("next")))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("auth.register", next=request.args.get("next")))

    # Pre-check to give a friendly message before we hit a DB constraint
    exists = (User.query.filter(func.lower(User.username) == username).first()
              or User.query.filter(func.lower(User.email) == email).first())
    if exists:
        flash("Username or email already taken.", "error")
        return redirect(url_for("auth.register", next=request.args.get("next")))

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role="student",
        is_active=True,
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Username or email already taken.", "error")
        return redirect(url_for("auth.register", next=request.args.get("next")))

    login_user(user)
    return redirect(_safe_next())

@auth_bp.get("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("home.index"))

# ----- Forgot password -----
@auth_bp.get("/forgot")
def forgot():
    if current_user.is_authenticated:
        return redirect(url_for("game24.play"))
    return render_template("auth/forgot.html")

@auth_bp.post("/forgot")
@limiter.limit("5 per minute")
def forgot_post():
    ident = (request.form.get("username_or_email") or "").strip().lower()
    if not ident:
        flash("Please enter your username or email.", "error")
        return redirect(url_for("auth.forgot"))

    user = (User.query.filter(func.lower(User.username) == ident).first()
            or User.query.filter(func.lower(User.email) == ident).first())

    # For privacy: do NOT reveal whether the account exists.
    # Always say "If an account exists, we've sent instructions."
    if user:
        token = _make_reset_token(user.id)
        link = url_for("auth.reset_with_token", token=token, _external=True)
        # send real email
        subject = "Reset your Little Teachers password"
        body = f"Hi {user.username},\n\nUse this link to reset your password:\n{link}\n\nThis link expires in {current_app.config['PASSWORD_RESET_TOKEN_AGE']//60} minutes."
        try:
            send_email(user.email, subject, body)
        except Exception as e:
            current_app.logger.error("Email send failed: %s", e)
            # Optional: fall back to dev link in flash during testing
            if current_app.debug:
                flash(f"DEV: reset link → {link}", "info")

        _dev_send_reset_link(link)  # dev helper below

    flash("If an account exists, we’ve sent password reset instructions.", "info")
    return redirect(url_for("auth.login"))

def _dev_send_reset_link(link: str):
    # DEV ONLY: show in server logs and flash so you can test without email
    current_app.logger.info("Password reset link: %s", link)
    # You can comment this out if you prefer not to show to the user:
    flash(f"DEV: reset link → {link}", "info")

# ----- Reset with token -----
@auth_bp.get("/reset/<token>")
def reset_with_token(token):
    # Only verify token age when user submits the new password.
    # For GET, we still try to parse so obviously-bad tokens 404.
    try:
        _ = _parse_reset_token(token, current_app.config["PASSWORD_RESET_TOKEN_AGE"])
    except (BadSignature, SignatureExpired):
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("auth.forgot"))
    return render_template("auth/reset.html", token=token)

@auth_bp.post("/reset/<token>")
def reset_with_token_post(token):
    password = request.form.get("password") or ""
    confirm  = request.form.get("confirm") or ""
    if not password or not confirm:
        flash("Please enter your new password twice.", "error")
        return redirect(url_for("auth.reset_with_token", token=token))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.reset_with_token", token=token))

    try:
        uid = _parse_reset_token(token, current_app.config["PASSWORD_RESET_TOKEN_AGE"])
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot"))
    except BadSignature:
        flash("Invalid reset link.", "error")
        return redirect(url_for("auth.forgot"))

    user = User.query.get(uid)
    if not user or not user.is_active:
        flash("Invalid account.", "error")
        return redirect(url_for("auth.forgot"))

    user.password_hash = generate_password_hash(password)
    db.session.commit()
    flash("Your password has been updated. Please sign in.", "success")
    return redirect(url_for("auth.login"))

#notes
#In DEV, you’ll see a flash like “DEV: reset link → http://127.0.0.1:5000/auth/reset/<token>”.
#In PROD, remove that flash and send the link via email (e.g., SendGrid/Mailgun/SES or SMTP).
