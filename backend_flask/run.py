import csv
import io
import time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

from flask import Flask, Blueprint, render_template, session, redirect, request
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

@main.route('/menu')
def menu():
    now = datetime.now(RIYADH)
    weekday = now.strftime('%A').lower()

    if weekday in ('friday', 'saturday'):
        return render_template('weekend_closed.html')

    try:
        rows = _fetch_menu_rows()
    except Exception as e:
        return render_template('menu_error.html', error=str(e)), 500

    sections = _build_sections(rows, weekday)
    weekday_en, weekday_ar = WEEKDAY_LABELS[weekday]
    return render_template(
        'menu.html',
        sections=sections,
        weekday_en=weekday_en,
        weekday_ar=weekday_ar,
    )

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
