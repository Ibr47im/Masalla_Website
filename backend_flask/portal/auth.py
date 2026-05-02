"""Auth: User class, login_manager hooks, role decorator."""
from functools import wraps

import bcrypt
from flask import abort
from flask_login import UserMixin, current_user

from .db import query_one


class User(UserMixin):
    def __init__(self, id, username, role, client_id=None, floor=None, active=True):
        self.id = id
        self.username = username
        self.role = role
        self.client_id = client_id
        self.floor = floor
        self.active = bool(active)

    @property
    def is_active(self):
        return self.active

    def get_id(self):
        return str(self.id)

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            client_id=row["client_id"],
            floor=row["floor"],
            active=row["active"],
        )


def load_user_by_id(user_id):
    row = query_one(
        "SELECT id, username, role, client_id, floor, active "
        "FROM users WHERE id = ? AND active = 1",
        (int(user_id),),
    )
    return User.from_row(row)


def load_user_by_username(username):
    row = query_one(
        "SELECT id, username, password_hash, role, client_id, floor, active "
        "FROM users WHERE username = ? AND active = 1",
        (username,),
    )
    return row  # raw row — caller needs password_hash


def hash_password(plaintext):
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext, hashed):
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def role_required(*roles):
    """Decorator that 403s if current_user.role isn't in the allowed set."""
    def wrapper(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return wrapper
