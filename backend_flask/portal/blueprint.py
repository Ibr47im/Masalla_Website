"""Portal blueprint: login, logout, dashboard."""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from . import db
from .auth import User, load_user_by_id, load_user_by_username, verify_password


portal_bp = Blueprint(
    "portal",
    __name__,
    template_folder="../templates/portal",
    static_folder="../static/portal",
    static_url_path="/portal/static",
)

login_manager = LoginManager()
login_manager.login_view = "portal.login"
login_manager.login_message = "Please log in to access the portal."
login_manager.login_message_category = "info"


@login_manager.user_loader
def _user_loader(user_id):
    return load_user_by_id(user_id)


def init_portal(app):
    """Wire blueprint, login_manager, and ensure DB schema exists."""
    db.ensure_initialized()
    login_manager.init_app(app)
    app.teardown_appcontext(db.close_db)

    # Hardening — applies to the whole app session cookie.
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    # Note: SESSION_COOKIE_SECURE intentionally NOT set here so local
    # http dev still works. Set via env for production if desired.


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@portal_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))
    return redirect(url_for("portal.login"))


@portal_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("login.html"), 400

        row = load_user_by_username(username)
        if row is None or not verify_password(password, row["password_hash"]):
            # Generic message — don't leak which field was wrong.
            flash("Invalid username or password.", "error")
            return render_template("login.html"), 401

        user = User.from_row(row)
        login_user(user)
        return redirect(url_for("portal.dashboard"))

    return render_template("login.html")


@portal_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("portal.login"))


@portal_bp.route("/dashboard")
@login_required
def dashboard():
    template = {
        "admin":  "dashboard_admin.html",
        "staff":  "dashboard_staff.html",
        "client": "dashboard_client.html",
    }.get(current_user.role, "dashboard_client.html")
    return render_template(template, user=current_user)
