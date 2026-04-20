import csv
import hashlib
import hmac
import html
import io
import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

from flask import Flask, Blueprint, render_template, session, redirect, request, jsonify
from jinja2 import ChoiceLoader, FileSystemLoader, TemplateNotFound

app = Flask(__name__)
app.secret_key = 'al7afozleeq-kwfellow'

# Allow {% include %} to find files in both templates/ and static/
app.jinja_loader = ChoiceLoader([
    FileSystemLoader('templates'),
    FileSystemLoader('static'),
])

main = Blueprint('main', __name__)

# ---------------------------------------------------------------------------
# Daily menu: data source, cache, schema
# ---------------------------------------------------------------------------

MENU_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vQH1WpksMmLcKaHnKDQf6"
    "dZrh413giKEIqGzaOIknXrHGzccOzrKJLJIxdnvsXlCQMvnJ6DdyP089hN/pub?output=csv"
)

# Riyadh is UTC+3 year-round (no DST) — a fixed offset keeps us off tzdata.
RIYADH = timezone(timedelta(hours=3), name="Asia/Riyadh")

MENU_CACHE_TTL = 300  # seconds
_menu_cache = {"ts": 0.0, "rows": None}

REQUIRED_COLS = {"day", "order", "category", "name_en", "name_ar"}
VALID_DAYS = {
    "sunday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "daily",
}

CATEGORY_LABELS = {
    "salad":         ("Salads",       "السلطات"),
    "sandwich":      ("Sandwiches",   "السندويتشات"),
    "main_course":   ("Main Courses", "الأطباق الرئيسية"),
    "dessert":       ("Desserts",     "الحلويات"),
    "assorted_cups": ("Cups",         "الكاسات"),
    "beverages":     ("Beverages",    "المشروبات"),
}

WEEKDAY_LABELS = {
    "sunday":    ("Sunday",    "الأحد"),
    "monday":    ("Monday",    "الاثنين"),
    "tuesday":   ("Tuesday",   "الثلاثاء"),
    "wednesday": ("Wednesday", "الأربعاء"),
    "thursday":  ("Thursday",  "الخميس"),
    "friday":    ("Friday",    "الجمعة"),
    "saturday":  ("Saturday",  "السبت"),
}


def _fetch_menu_rows():
    """Fetch + validate the menu CSV. Cached for MENU_CACHE_TTL seconds."""
    now = time.time()
    if _menu_cache["rows"] is not None and now - _menu_cache["ts"] < MENU_CACHE_TTL:
        return _menu_cache["rows"]

    req = Request(MENU_SHEET_URL, headers={"User-Agent": "Masalla-Menu/1.0"})
    with urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not REQUIRED_COLS.issubset(set(reader.fieldnames)):
        raise ValueError(
            f"Menu sheet missing required columns. "
            f"Expected {sorted(REQUIRED_COLS)}, got {reader.fieldnames}"
        )

    rows = []
    for i, raw in enumerate(reader, start=2):  # row 1 is header
        name_en = (raw.get("name_en") or "").strip()
        name_ar = (raw.get("name_ar") or "").strip()
        if not name_en and not name_ar:
            continue  # skip blank rows

        # "available" column: default True when column missing or cell blank.
        # Only explicit FALSE/false/0 excludes the row.
        available_raw = (raw.get("available") or "").strip().upper()
        if available_raw in ("FALSE", "0", "NO"):
            continue

        day = (raw.get("day") or "").strip().lower()
        if day not in VALID_DAYS:
            raise ValueError(f"Row {i}: invalid day '{raw.get('day')}'")

        try:
            order = int((raw.get("order") or "").strip())
        except ValueError:
            raise ValueError(f"Row {i}: invalid order '{raw.get('order')}'")

        category = (raw.get("category") or "").strip().lower()
        if not category:
            raise ValueError(f"Row {i}: category is required")

        rows.append({
            "day": day,
            "order": order,
            "category": category,
            "name_en": name_en,
            "name_ar": name_ar,
        })

    _menu_cache["rows"] = rows
    _menu_cache["ts"] = now
    return rows


def _build_sections(rows, weekday):
    """Filter to today + daily, group by category, keep section order stable."""
    relevant = [r for r in rows if r["day"] in (weekday, "daily")]

    by_cat = {}
    for r in relevant:
        bucket = by_cat.setdefault(r["category"], {"order": r["order"], "dishes": []})
        bucket["dishes"].append(r)

    sections = []
    for cat, data in sorted(by_cat.items(), key=lambda kv: kv[1]["order"]):
        label_en, label_ar = CATEGORY_LABELS.get(
            cat, (cat.replace("_", " ").title(), cat)
        )
        sections.append({
            "key": cat,
            "label_en": label_en,
            "label_ar": label_ar,
            "dishes": data["dishes"],
        })
    return sections


def get_lang():
    return session.get('lang', 'en')

@app.context_processor
def inject_lang():
    return {'lang': get_lang()}

@main.route('/')
def index():
    return render_template(f'{get_lang()}/index.html')

@main.route('/gallery')
def gallery():
    return render_template(f'{get_lang()}/gallery.html')

AR_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def _effective_weekday(now):
    """Menu rollover: Saturday 20:00+ shows Sunday's menu."""
    weekday = now.strftime('%A').lower()
    if weekday == 'saturday' and now.hour >= 20:
        return 'sunday'
    return weekday


def _effective_date(now):
    """Date matching the effective weekday (shifted on Saturday rollover)."""
    if now.strftime('%A').lower() == 'saturday' and now.hour >= 20:
        return now + timedelta(days=1)
    return now


def _format_date(d):
    date_en = f"{d.strftime('%B')} {d.day}, {d.year}"
    ar_digits = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    date_ar = f"{d.day} {AR_MONTHS[d.month]} {d.year}".translate(ar_digits)
    return date_en, date_ar


@main.route('/menu')
def menu():
    now = datetime.now(RIYADH)
    weekday = _effective_weekday(now)

    if weekday in ('friday', 'saturday'):
        return render_template('weekend_closed.html')

    try:
        rows = _fetch_menu_rows()
    except Exception as e:
        return render_template('menu_error.html', error=str(e)), 500

    sections = _build_sections(rows, weekday)
    weekday_en, weekday_ar = WEEKDAY_LABELS[weekday]
    date_en, date_ar = _format_date(_effective_date(now))
    return render_template(
        'menu.html',
        sections=sections,
        weekday_en=weekday_en,
        weekday_ar=weekday_ar,
        date_en=date_en,
        date_ar=date_ar,
    )

# ---------------------------------------------------------------------------
# Review submission → Google Apps Script webhook
# ---------------------------------------------------------------------------

REVIEW_SCRIPT_URL = (
    "https://script.google.com/macros/s/AKfycbxDPfM48lv46UCPl4VNdSRrbc"
    "WvGFVeY14AmoiskyF2m3IlmR8NQE0aubPLVFWbfWtk/exec"
)

RATING_FIELDS = ("rating_service", "rating_heat", "rating_taste", "rating_overall")

_review_limits = {}
REVIEW_RATE_LIMIT = 10
REVIEW_RATE_WINDOW = 3600


def _check_rate_limit(ip):
    now = time.time()
    entries = _review_limits.get(ip, [])
    entries = [t for t in entries if now - t < REVIEW_RATE_WINDOW]
    if len(entries) >= REVIEW_RATE_LIMIT:
        return False
    entries.append(now)
    _review_limits[ip] = entries
    return True


@main.route('/menu/review', methods=['POST'])
def submit_review():
    if not request.is_json:
        return jsonify({"error": "Invalid content type"}), 400

    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        return jsonify({"error": "Too many submissions. Please try later."}), 429

    data = request.get_json(silent=True) or {}

    ratings = {}
    for field in RATING_FIELDS:
        val = data.get(field)
        if not isinstance(val, int) or not 1 <= val <= 5:
            return jsonify({"error": f"All ratings are required (1–5)"}), 400
        ratings[field] = val

    comment = html.escape(str(data.get("comment", ""))[:500]).strip()
    name = html.escape(str(data.get("name", ""))[:100]).strip()

    now = datetime.now(RIYADH)
    weekday = now.strftime('%A').lower()

    payload = json.dumps({
        "timestamp": now.isoformat(),
        "weekday": weekday,
        **ratings,
        "comment": comment,
        "name": name,
    }).encode("utf-8")

    try:
        req = Request(
            REVIEW_SCRIPT_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Masalla-Menu/1.0",
            },
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception:
        return jsonify({"error": "Could not save review. Please try again."}), 502

    return jsonify({"ok": True}), 201


# ---------------------------------------------------------------------------
# GitHub webhook → auto-deploy on push to main
# ---------------------------------------------------------------------------

GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
DEPLOY_SCRIPT = "/opt/masalla/deploy.sh"


@main.route('/webhook/github', methods=['POST'])
def github_webhook():
    if not GITHUB_WEBHOOK_SECRET:
        return jsonify({"error": "Webhook not configured"}), 503

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        return jsonify({"error": "Missing signature"}), 401

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        request.get_data(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return jsonify({"error": "Invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    if payload.get("ref") != "refs/heads/main":
        return jsonify({"ok": True, "skipped": "not main branch"}), 200

    subprocess.Popen(
        ["/usr/bin/sudo", DEPLOY_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return jsonify({"ok": True, "deploying": True}), 202


@main.route('/set_lang/<lang_code>')
def set_lang(lang_code):
    if lang_code in ['en', 'ar']:
        session['lang'] = lang_code
    return redirect(request.referrer or '/')

@app.errorhandler(404)
def page_not_found(_e):
    return render_template(f'{get_lang()}/404.html'), 404

@app.errorhandler(TemplateNotFound)
def template_missing(_e):
    return render_template(f'{get_lang()}/404.html'), 404

app.register_blueprint(main)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
