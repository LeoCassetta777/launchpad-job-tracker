"""Launchpad: start here.

Run it with:  python app.py   then open http://127.0.0.1:5050

This file creates the Flask app, connects the JSON APIs (api.py, api_ai.py,
api_notify.py), serves the pages, and starts the reminder scheduler. The pages
are mostly empty HTML shells; the JavaScript in static/js fetches data from /api
and draws the cards.
"""
import os

from flask import Flask, abort, render_template, request

import auth
import clipper
import config
import constants
import db
import seed
from api import api
from api_ai import api_ai
from api_notify import api_notify
from api_prep import api_prep
from api_focus import api_focus
from api_sync import api_sync


def app_origin():
    """The address the browser uses for Launchpad, e.g. http://127.0.0.1:5050 (APP_URL wins if set)."""
    return config.APP_URL or request.host_url.rstrip("/")


def create_app():
    app = Flask(__name__)
    app.json.ensure_ascii = False        # send emoji as-is in JSON
    app.teardown_appcontext(db.close_db)
    auth.init(app)          # optional password login (off unless set_password.py was run)
    app.register_blueprint(api)
    app.register_blueprint(api_ai)
    app.register_blueprint(api_notify)
    app.register_blueprint(api_prep)
    app.register_blueprint(api_focus)
    app.register_blueprint(api_sync)      # Discover + Canvas
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024   # uploads: 10 MB file + form fields
    db.init_db()

    @app.template_filter("nicedate")
    def nicedate(value):
        """'2026-11-07' -> 'Sat, Nov 7' (used in emails)."""
        from datetime import date
        d = date.fromisoformat(value) if isinstance(value, str) else value
        return f"{d:%a, %b} {d.day}"

    app.add_template_filter(config.clock, "clock")    # '14:00' -> '2:00 PM'

    @app.context_processor
    def shared_template_values():
        # Available in every template: the choice lists, today's date (Eastern), and
        # whether AI is configured (just true/false; the key never reaches the browser).
        return {"constants": constants.as_dict(), "today": config.today_str(), "ai_enabled": config.AI_ENABLED}

    @app.get("/")
    def pipeline():
        return render_template("pipeline.html", page="pipeline")

    @app.get("/week")
    def week():
        return render_template("week.html", page="week")

    @app.get("/contacts")
    def contacts():
        return render_template("contacts.html", page="contacts")

    @app.get("/contacts/<int:contact_id>")
    def contact_page(contact_id):
        row = db.get_db().execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if row is None:
            abort(404)
        return render_template("contact.html", page="contacts", contact_id=contact_id)

    @app.get("/documents")
    def documents_page():
        return render_template("documents.html", page="documents")

    @app.get("/questions")
    def questions_page():
        return render_template("questions.html", page="questions")

    @app.get("/rejections")
    def rejections_page():
        return render_template("rejections.html", page="rejections")

    @app.get("/prep/<int:opp_id>")
    def prep_page(opp_id):
        if db.get_db().execute("SELECT id FROM opportunities WHERE id = ?", (opp_id,)).fetchone() is None:
            abort(404)
        return render_template("prep.html", page="questions", opp_id=opp_id)

    # Phase 5 pages
    @app.get("/matrix")
    def matrix_page():
        return render_template("matrix.html", page="matrix")

    @app.get("/stats")
    def stats_page():
        return render_template("stats.html", page="stats")

    @app.get("/shutdown")
    def shutdown_page():
        return render_template("shutdown.html", page="shutdown")

    @app.get("/review")
    def review_page():
        return render_template("review.html", page="review")

    @app.get("/talk")
    def talk_page():
        return render_template("talk.html", page="talk")

    @app.get("/discover")
    def discover_page():
        return render_template("discover.html", page="discover")

    @app.get("/school")
    def school_page():
        return render_template("school.html", page="school")

    @app.get("/guide")
    def guide_page():
        return render_template("guide.html", page="guide")

    @app.get("/settings")
    def settings():
        origin = app_origin()
        conn = db.get_db()
        return render_template(
            "settings.html", page="settings",
            bookmarklet=clipper.bookmarklet_href(origin),
            bookmarklet_source=clipper.readable_source(origin),
            origin=origin,
            parse_model=config.PARSE_MODEL, smart_model=config.SMART_MODEL,
            has_demo=seed.has_seed_data(conn),
        )

    @app.route("/clip", methods=["GET", "POST"])
    def clip():
        """Landing page for the bookmarklet. It only pre-fills the paste-a-posting box; nothing is saved.

        POST: the bookmarklet's hidden form sent url/title/text.
        GET:  the backup path; the page asks the opener tab for the data with postMessage.
        """
        clip_data = None
        if request.method == "POST":
            clip_data = {
                "url": request.form.get("url", "")[:1000],
                "title": request.form.get("title", "")[:300],
                "text": request.form.get("text", "")[:60000],
                "selected": request.form.get("selected") == "1",
            }
        return render_template("clip.html", page="clip", clip_data=clip_data)

    return app


app = create_app()

if __name__ == "__main__":
    # In debug mode Flask runs two processes (a file watcher + the real server).
    # Only start reminders in the real one, so checks never run twice.
    if not config.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        import scheduler
        scheduler.start(app)
    print(f"\n  Launchpad running at http://{config.HOST}:{config.PORT}\n  Database: {config.DB_PATH}\n")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
