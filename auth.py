"""Single-password login: a second lock behind Tailscale.

Off unless LAUNCHPAD_PASSWORD_HASH is set in .env (set it with set_password.py).
Only a hash of the password is stored (scrypt, via Werkzeug), never the password.

    Logged in   = a signed session cookie, good for 30 days on that device/browser.
    Pages       redirect to /login?next=... and come back after you log in.
    API calls   get 401, and the page sends you to the login screen.
    Too many wrong tries: after 5 in a row, logins pause for 60 seconds.

Cookie settings on https (the Mac mini): Secure + HttpOnly + SameSite=None.
SameSite=None lets the clipper bookmarklet's form (sent from a job site) arrive
logged in. That's safe here because every change to your data must be JSON or
carry the X-Launchpad header, which other websites can't send (see api.py).
"""
import secrets
import time
from datetime import timedelta
from urllib.parse import urlparse

from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import config

OPEN_PREFIXES = ("/login", "/static/")
MAX_TRIES, LOCK_SECONDS = 5, 60
_state = {"fails": 0, "locked_until": 0.0}


def enabled():
    return bool(config.PASSWORD_HASH)


def _safe_next(target):
    """Only allow redirects to pages on this site (no '//evil.com' tricks)."""
    if not target:
        return "/"
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


def init(app):
    https = config.app_base_url().startswith("https://")
    app.secret_key = config.SECRET_KEY or secrets.token_hex(32)   # random if unset: logins reset on restart
    app.config.update(
        SESSION_COOKIE_NAME="launchpad_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=https,
        SESSION_COOKIE_SAMESITE="None" if https else "Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    @app.context_processor
    def login_flag():
        return {"login_enabled": enabled()}

    @app.before_request
    def require_login():
        if not enabled() or request.path.startswith(OPEN_PREFIXES) or session.get("ok"):
            return None
        if request.path == "/clip" and request.method == "POST":
            # The clipped text can't survive a redirect; ask to log in, then clip again.
            return render_template("login.html", message="Log in, then click the clipper again.",
                                   next="/"), 401
        if request.path.startswith("/api/") or request.method != "GET":
            return jsonify(error="Please log in again."), 401
        return redirect(url_for("login", next=request.full_path.rstrip("?")))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        nxt = _safe_next(request.values.get("next"))
        if not enabled():
            return redirect(nxt)
        if request.method == "GET":
            return render_template("login.html", next=nxt)
        now = time.time()
        if now < _state["locked_until"]:
            wait = int(_state["locked_until"] - now) + 1
            return render_template("login.html", next=nxt, message=f"Too many tries. Wait {wait} seconds."), 429
        if check_password_hash(config.PASSWORD_HASH, request.form.get("password", "")):
            _state["fails"] = 0
            session.clear()
            session.permanent = True
            session["ok"] = True
            return redirect(nxt)
        _state["fails"] += 1
        if _state["fails"] >= MAX_TRIES:
            _state["fails"] = 0
            _state["locked_until"] = now + LOCK_SECONDS
        return render_template("login.html", next=nxt, message="That's not the password."), 401

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
