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
