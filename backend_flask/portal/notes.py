"""Delivery-note routes: list, create, view, confirm, void."""
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
)
from flask_login import login_required, current_user

from . import db
from .csrf import validate_request


notes_bp = Blueprint(
    "notes",
    __name__,
    template_folder="../templates/portal/notes",
)


@notes_bp.before_request
@login_required
def _gate():
    validate_request()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _next_note_number(conn):
    """DN-YYYY-NNNN — sequence resets per year."""
    year = datetime.now().year
    prefix = f"DN-{year}-"
    row = conn.execute(
        "SELECT note_number FROM delivery_notes "
        "WHERE note_number LIKE ? ORDER BY id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    if row:
        try:
            seq = int(row["note_number"].rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def _can_view(note):
    """True if current_user is allowed to see this note."""
    if current_user.role == "admin":
        return True
    if current_user.role == "staff":
        return (note["created_by"] == current_user.id
                or note["floor"] == current_user.floor)
    if current_user.role == "client":
        return (note["client_id"] == current_user.client_id
                and note["floor"] == current_user.floor)
    return False


def _can_confirm(note):
    """True if current_user can confirm this pending note."""
    if note["status"] != "pending":
        return False
    if current_user.role == "admin":
        return True
    if current_user.role == "client":
        return (note["client_id"] == current_user.client_id
                and note["floor"] == current_user.floor)
    return False


def _can_void(note):
    """Admin: any non-voided. Staff: own pending only."""
    if note["status"] == "voided":
        return False
    if current_user.role == "admin":
        return True
    if current_user.role == "staff":
        return (note["created_by"] == current_user.id
                and note["status"] == "pending")
    return False


def _load_note(note_id):
    note = db.query_one(
        "SELECT n.*, c.name AS client_name, "
        "       u.username AS created_by_name, "
        "       v.username AS voided_by_name "
        "FROM delivery_notes n "
        "JOIN clients c ON c.id = n.client_id "
        "JOIN users u ON u.id = n.created_by "
        "LEFT JOIN users v ON v.id = n.voided_by "
        "WHERE n.id = ?",
        (note_id,),
    )
    if not note:
        abort(404)
    return note


def _load_items(note_id):
    return db.query_all(
        "SELECT id, sort_order, name_en, name_ar, staff_quantity, client_quantity "
        "FROM delivery_items WHERE note_id = ? ORDER BY sort_order, id",
        (note_id,),
    )


# ----------------------------------------------------------------------
# Notes list
# ----------------------------------------------------------------------

@notes_bp.route("/notes")
def notes_list():
    if current_user.role == "admin":
        rows = db.query_all(
            "SELECT n.id, n.note_number, n.floor, n.status, n.created_at, "
            "       c.name AS client_name, u.username AS created_by_name "
            "FROM delivery_notes n "
            "JOIN clients c ON c.id = n.client_id "
            "JOIN users u ON u.id = n.created_by "
            "ORDER BY n.id DESC"
        )
    elif current_user.role == "staff":
        rows = db.query_all(
            "SELECT n.id, n.note_number, n.floor, n.status, n.created_at, "
            "       c.name AS client_name, u.username AS created_by_name "
            "FROM delivery_notes n "
            "JOIN clients c ON c.id = n.client_id "
            "JOIN users u ON u.id = n.created_by "
            "WHERE n.created_by = ? OR n.floor = ? "
            "ORDER BY n.id DESC",
            (current_user.id, current_user.floor),
        )
    else:  # client
        rows = db.query_all(
            "SELECT n.id, n.note_number, n.floor, n.status, n.created_at, "
            "       c.name AS client_name, u.username AS created_by_name "
            "FROM delivery_notes n "
            "JOIN clients c ON c.id = n.client_id "
            "JOIN users u ON u.id = n.created_by "
            "WHERE n.client_id = ? AND n.floor = ? "
            "ORDER BY n.id DESC",
            (current_user.client_id, current_user.floor),
        )
    return render_template("notes/list.html", notes=rows)


# ----------------------------------------------------------------------
# New note
# ----------------------------------------------------------------------

@notes_bp.route("/notes/new", methods=["GET", "POST"])
def note_new():
    if current_user.role not in ("admin", "staff"):
        abort(403)

    clients = db.query_all(
        "SELECT id, name FROM clients WHERE active = 1 ORDER BY name"
    )

    if request.method == "POST":
        try:
            client_id = int(request.form.get("client_id") or 0)
            floor = int(request.form.get("floor") or 0)
        except ValueError:
            flash("Invalid client or floor.", "error")
            return redirect(url_for("portal.notes.note_new"))

        if floor <= 0:
            flash("Floor must be a positive number.", "error")
            return redirect(url_for("portal.notes.note_new"))

        if not db.query_one(
            "SELECT id FROM clients WHERE id = ? AND active = 1", (client_id,)
        ):
            flash("Selected client doesn't exist.", "error")
            return redirect(url_for("portal.notes.note_new"))

        # Items posted as parallel arrays: name_en[], name_ar[], qty[]
        names_en = request.form.getlist("name_en")
        names_ar = request.form.getlist("name_ar")
        qtys = request.form.getlist("qty")

        items = []
        for i, name_en in enumerate(names_en):
            name_en = name_en.strip()
            if not name_en:
                continue
            try:
                qty = int(qtys[i] or 0)
            except ValueError:
                qty = 0
            if qty < 0:
                qty = 0
            name_ar = (names_ar[i].strip() if i < len(names_ar) else "")
            items.append((name_en, name_ar or None, qty))

        if not items:
            flash("Add at least one item.", "error")
            return render_template(
                "notes/new.html",
                clients=clients,
                form_data={"client_id": client_id, "floor": floor,
                           "notes": request.form.get("notes", "")},
            ), 400

        notes_text = (request.form.get("notes") or "").strip() or None

        conn = db.get_db()
        with conn:
            note_number = _next_note_number(conn)
            cursor = conn.execute(
                "INSERT INTO delivery_notes "
                "(note_number, client_id, floor, status, created_by, notes) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (note_number, client_id, floor, current_user.id, notes_text),
            )
            note_id = cursor.lastrowid
            for sort_order, (name_en, name_ar, qty) in enumerate(items, start=1):
                conn.execute(
                    "INSERT INTO delivery_items "
                    "(note_id, sort_order, name_en, name_ar, staff_quantity) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (note_id, sort_order, name_en, name_ar, qty),
                )

        flash(f"Created note {note_number}.", "success")
        return redirect(url_for("portal.notes.note_view", note_id=note_id))

    # GET — pre-select staff's floor
    default_floor = current_user.floor or ""
    return render_template(
        "notes/new.html",
        clients=clients,
        form_data={"floor": default_floor, "client_id": (clients[0]["id"] if clients else None)},
    )


# ----------------------------------------------------------------------
# View / confirm / void
# ----------------------------------------------------------------------

@notes_bp.route("/notes/<int:note_id>")
def note_view(note_id):
    note = _load_note(note_id)
    if not _can_view(note):
        abort(403)
    items = _load_items(note_id)

    has_discrepancy = any(
        it["client_quantity"] is not None
        and it["client_quantity"] != it["staff_quantity"]
        for it in items
    )

    return render_template(
        "notes/view.html",
        note=note,
        items=items,
        can_confirm=_can_confirm(note),
        can_void=_can_void(note),
        has_discrepancy=has_discrepancy,
    )


@notes_bp.route("/notes/<int:note_id>/confirm", methods=["POST"])
def note_confirm(note_id):
    note = _load_note(note_id)
    if not _can_confirm(note):
        abort(403)

    items = _load_items(note_id)

    confirmed_name = (request.form.get("confirmed_name") or "").strip()
    if not confirmed_name or len(confirmed_name) > 100:
        flash("Please enter your name (max 100 chars).", "error")
        return redirect(url_for("portal.notes.note_view", note_id=note_id))

    # Each item posts client_qty_<id>
    updates = []
    for it in items:
        raw = request.form.get(f"client_qty_{it['id']}", "")
        try:
            qty = int(raw)
            if qty < 0:
                raise ValueError
        except ValueError:
            flash(f"Invalid quantity for '{it['name_en']}'.", "error")
            return redirect(url_for("portal.notes.note_view", note_id=note_id))
        updates.append((qty, it["id"]))

    conn = db.get_db()
    with conn:
        for qty, item_id in updates:
            conn.execute(
                "UPDATE delivery_items SET client_quantity = ? WHERE id = ?",
                (qty, item_id),
            )
        conn.execute(
            "UPDATE delivery_notes SET status = 'confirmed', "
            "confirmed_by_name = ?, confirmed_at = datetime('now') "
            "WHERE id = ?",
            (confirmed_name, note_id),
        )

    flash("Delivery confirmed. Thank you.", "success")
    return redirect(url_for("portal.notes.note_view", note_id=note_id))


@notes_bp.route("/notes/<int:note_id>/void", methods=["POST"])
def note_void(note_id):
    note = _load_note(note_id)
    if not _can_void(note):
        abort(403)

    reason = (request.form.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        flash("Void reason is required (max 500 chars).", "error")
        return redirect(url_for("portal.notes.note_view", note_id=note_id))

    db.execute(
        "UPDATE delivery_notes SET status = 'voided', "
        "voided_by = ?, voided_at = datetime('now'), voided_reason = ? "
        "WHERE id = ?",
        (current_user.id, reason, note_id),
    )
    flash(f"Note {note['note_number']} voided.", "success")
    return redirect(url_for("portal.notes.note_view", note_id=note_id))


# ----------------------------------------------------------------------
# Menu import API (used by new-note page JS)
# ----------------------------------------------------------------------

@notes_bp.route("/api/menu-today")
def api_menu_today():
    """Return today's menu items as JSON for pre-filling new notes."""
    if current_user.role not in ("admin", "staff"):
        abort(403)

    # Imported lazily so portal works even if menu fetch breaks.
    try:
        from run import (
            _fetch_menu_rows, _build_sections, _effective_weekday, RIYADH
        )
    except Exception as e:
        return jsonify({"error": f"Menu module unavailable: {e}"}), 500

    try:
        rows = _fetch_menu_rows()
    except Exception as e:
        return jsonify({"error": f"Could not fetch menu: {e}"}), 502

    weekday = _effective_weekday(datetime.now(RIYADH))
    sections = _build_sections(rows, weekday)

    items = []
    for section in sections:
        for dish in section["dishes"]:
            items.append({
                "name_en": dish["name_en"],
                "name_ar": dish.get("name_ar") or "",
                "category": section["label_en"],
            })
    return jsonify({"weekday": weekday, "items": items})
