"""CLI bootstrap. Run from backend_flask/ as:

    python -m portal.cli init-db
    python -m portal.cli create-admin --username ahmed
    python -m portal.cli create-admin --username ahmed --password s3cret
"""
import argparse
import getpass
import sys

from . import db
from .auth import hash_password


def cmd_init_db(_args):
    db.ensure_initialized()
    print(f"Schema ensured at: {db.get_db_path()}")


def cmd_create_admin(args):
    db.ensure_initialized()

    username = args.username.strip()
    if not username:
        print("ERROR: --username is required and non-empty.", file=sys.stderr)
        sys.exit(2)

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm:  ")
        if password != confirm:
            print("ERROR: passwords do not match.", file=sys.stderr)
            sys.exit(1)
    if len(password) < 8:
        print("ERROR: password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    conn = db.open_standalone()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing is not None:
            print(f"ERROR: user '{username}' already exists.", file=sys.stderr)
            sys.exit(1)

        conn.execute(
            "INSERT INTO users (username, password_hash, role, active) "
            "VALUES (?, ?, 'admin', 1)",
            (username, hash_password(password)),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Created admin user '{username}'.")


def main():
    parser = argparse.ArgumentParser(prog="portal.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create schema if missing").set_defaults(
        func=cmd_init_db
    )

    p_admin = sub.add_parser("create-admin", help="Create the first admin user")
    p_admin.add_argument("--username", required=True)
    p_admin.add_argument("--password", help="Skip prompt (less safe in shell history)")
    p_admin.set_defaults(func=cmd_create_admin)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
