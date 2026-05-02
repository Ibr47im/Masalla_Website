"""Admin-only routes: manage users + clients."""
import re

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort
)
from flask_login import login_required, current_user

from . import db
from .auth import role_required, hash_password
from .csrf import validate_request


admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="../templates/portal/admin",
)


# All admin routes require: logged-in + admin role + valid CSRF on writes.
@admin_bp.before_request
@login_required
def _gate():
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)
    validate_request()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")
VALID_ROLES = ("admin", "staff", "client")


def _validate_user_form(form, *, require_password):
    """Returns (data, errors). Caller redisplays form if errors non-empty."""
    errors = []
    username = (form.get("username") or "").strip()
    role = (form.get("role") or "").strip()
    floor_raw = (form.get("floor") or "").strip()
    client_id_raw = (form.get("client_id") or "").strip()
    password = form.get("password") or ""
    active = 1 if form.get("active") == "on" else 0

    if not USERNAME_RE.match(username):
        errors.append("Username must be 3–32 chars: letters, numbers, dot, dash, underscore.")
    if role not in VALID_ROLES:
        errors.append("Role must be admin, staff, or client.")

    floor = None
    if role in ("staff", "client"):
        if not floor_raw:
            errors.append("Floor is required for staff and client.")
        else:
            try:
                floor = int(floor_raw)
                if floor < 0:
                    raise ValueError
            except ValueError:
                errors.append("Floor must be a non-negative integer.")

    client_id = None
    if role == "client":
        if not client_id_raw:
            errors.append("Client is required when role is 'client'.")
        else:
            try:
                client_id = int(client_id_raw)
            except ValueError:
                errors.append("Invalid client.")
            else:
                exists = db.query_one(
                    "SELECT id FROM clients WHERE id = ? AND active = 1",
                    (client_id,),
                )
                if not exists:
                    errors.append("Selected client doesn't exist or is inactive.")

    if require_password:
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
    elif password and len(password) < 8:
        # Optional change-password on edit
        errors.append("New password must be at least 8 characters.")

    return {
        "username": username,
        "role": role,
        "floor": floor,
        "client_id": client_id,
        "active": active,
        "password": password,
    }, errors


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------

@admin_bp.route("/users")
def users_list():
    rows = db.query_all(
        "SELECT u.id, u.username, u.role, u.floor, u.active, u.created_at, "
        "       c.name AS client_name "
        "FROM users u LEFT JOIN clients c ON c.id = u.client_id "
        "ORDER BY u.active DESC, u.role, u.username"
    )
    return render_template("admin/users_list.html", users=rows)


@admin_bp.route("/users/new", methods=["GET", "POST"])
def user_new():
    clients = db.query_all(
        "SELECT id, name FROM clients WHERE active = 1 ORDER BY name"
    )

    if request.method == "POST":
        data, errors = _validate_user_form(request.form, require_password=True)

        # Username uniqueness
        if not errors:
            existing = db.query_one(
                "SELECT id FROM users WHERE username = ?", (data["username"],)
            )
            if existing:
                errors.append(f"Username '{data['username']}' already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/user_form.html",
                clients=clients, form_data=data, mode="new",
            ), 400

        db.execute(
            "INSERT INTO users (username, password_hash, role, client_id, floor, active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (data["username"], hash_password(data["password"]),
             data["role"], data["client_id"], data["floor"], data["active"]),
        )
        flash(f"Created user '{data['username']}'.", "success")
        return redirect(url_for("portal.admin.users_list"))

    return render_template(
        "admin/user_form.html",
        clients=clients,
        form_data={"role": "staff", "active": 1},
        mode="new",
    )


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def user_edit(user_id):
    user = db.query_one(
        "SELECT id, username, role, client_id, floor, active FROM users WHERE id = ?",
        (user_id,),
    )
    if not user:
        abort(404)
    clients = db.query_all(
        "SELECT id, name FROM clients WHERE active = 1 ORDER BY name"
    )

    if request.method == "POST":
        data, errors = _validate_user_form(request.form, require_password=False)

        # Username uniqueness (excluding self)
        if not errors:
            existing = db.query_one(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (data["username"], user_id),
            )
            if existing:
                errors.append(f"Username '{data['username']}' already taken.")

        # Don't let admin demote/disable themselves
        if user_id == current_user.id:
            if data["role"] != "admin":
                errors.append("You cannot change your own role.")
            if data["active"] != 1:
                errors.append("You cannot deactivate yourself.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/user_form.html",
                clients=clients, form_data=data, mode="edit", user_id=user_id,
            ), 400

        # Build dynamic UPDATE — include password only if provided
        if data["password"]:
            db.execute(
                "UPDATE users SET username=?, password_hash=?, role=?, "
                "client_id=?, floor=?, active=? WHERE id=?",
                (data["username"], hash_password(data["password"]), data["role"],
                 data["client_id"], data["floor"], data["active"], user_id),
            )
        else:
            db.execute(
                "UPDATE users SET username=?, role=?, client_id=?, floor=?, active=? "
                "WHERE id=?",
                (data["username"], data["role"], data["client_id"],
                 data["floor"], data["active"], user_id),
            )
        flash(f"Updated user '{data['username']}'.", "success")
        return redirect(url_for("portal.admin.users_list"))

    form_data = dict(user)
    return render_template(
        "admin/user_form.html",
        clients=clients, form_data=form_data, mode="edit", user_id=user_id,
    )


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def user_toggle(user_id):
    """Activate or deactivate. Cannot self-deactivate."""
    if user_id == current_user.id:
        flash("You cannot deactivate yourself.", "error")
        return redirect(url_for("portal.admin.users_list"))

    user = db.query_one("SELECT id, username, active FROM users WHERE id = ?", (user_id,))
    if not user:
        abort(404)
    new_active = 0 if user["active"] else 1
    db.execute("UPDATE users SET active = ? WHERE id = ?", (new_active, user_id))
    flash(
        f"User '{user['username']}' "
        f"{'activated' if new_active else 'deactivated'}.",
        "success",
    )
    return redirect(url_for("portal.admin.users_list"))


# ----------------------------------------------------------------------
# Clients
# ----------------------------------------------------------------------

@admin_bp.route("/clients")
def clients_list():
    rows = db.query_all(
        "SELECT c.id, c.name, c.active, c.created_at, "
        "  (SELECT COUNT(*) FROM users WHERE client_id = c.id AND active = 1) AS user_count "
        "FROM clients c ORDER BY c.active DESC, c.name"
    )
    return render_template("admin/clients_list.html", clients=rows)


@admin_bp.route("/clients/new", methods=["GET", "POST"])
def client_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name or len(name) > 200:
            flash("Client name is required (max 200 chars).", "error")
            return render_template("admin/client_form.html",
                                   form_data={"name": name}, mode="new"), 400
        db.execute("INSERT INTO clients (name, active) VALUES (?, 1)", (name,))
        flash(f"Created client '{name}'.", "success")
        return redirect(url_for("portal.admin.clients_list"))

    return render_template("admin/client_form.html",
                           form_data={"name": ""}, mode="new")


@admin_bp.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def client_edit(client_id):
    client = db.query_one(
        "SELECT id, name, active FROM clients WHERE id = ?", (client_id,)
    )
    if not client:
        abort(404)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        active = 1 if request.form.get("active") == "on" else 0

        if not name or len(name) > 200:
            flash("Client name is required (max 200 chars).", "error")
            return render_template(
                "admin/client_form.html",
                form_data={"name": name, "active": active},
                mode="edit", client_id=client_id,
            ), 400

        db.execute(
            "UPDATE clients SET name=?, active=? WHERE id=?",
            (name, active, client_id),
        )
        flash(f"Updated client '{name}'.", "success")
        return redirect(url_for("portal.admin.clients_list"))

    return render_template(
        "admin/client_form.html",
        form_data=dict(client),
        mode="edit", client_id=client_id,
    )
