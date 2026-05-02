"""Minimal session-based CSRF token. Wired as a Jinja global."""
import hmac
import secrets

from flask import session, request, abort


_SESSION_KEY = "_portal_csrf"


def get_token():
    """Returns the per-session token, generating one on first use."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def validate_request():
    """Reject the current POST if its csrf_token field doesn't match the session token."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    submitted = request.form.get("csrf_token", "")
    expected = session.get(_SESSION_KEY, "")
    if not expected or not hmac.compare_digest(submitted, expected):
        abort(400, description="CSRF token missing or invalid.")
