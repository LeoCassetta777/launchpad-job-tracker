"""Runs the reminder checks in the background, every 15 minutes, while Launchpad is running.

Started from app.py. Two safeguards keep it from running twice:
  1. Flask's debug mode starts the app in TWO processes (a watcher that reloads on
     code changes, plus the real server). app.py only starts the scheduler in the
     real one (the process where WERKZEUG_RUN_MAIN is "true", or when debug is off).
  2. Even if two copies ever ran, notify.claim() lets each reminder be recorded
     only once, so nothing would be sent twice.
"""
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import config
import db
import reminders

log = logging.getLogger("launchpad.scheduler")
_scheduler = None


def _job(app):
    with app.app_context():            # emails are rendered with Flask templates
        conn = db.connect()
        try:
            for line in reminders.run_checks(conn):
                log.warning("%s", line)  # WARNING so it shows in the terminal by default
        except Exception:
            log.exception("Reminder check failed")
        finally:
            conn.close()


def _sync_job(app, name):
    """Discover (job postings) or the Canvas sync. Each logs what it did and never crashes the scheduler."""
    import canvas_sync
    import discover
    with app.app_context():            # the AI helper and emails need Flask's app context
        conn = db.connect()
        try:
            if name == "sweep":
                import settings_store
                if settings_store.get_all(conn)["discover_sweep"] != "1":
                    return
                result = discover.web_sweep(conn)
            else:
                result = (discover if name == "discover" else canvas_sync).run(conn)
            for line in result["log"]:
                log.warning("%s: %s", name, line)
        except Exception:
            log.exception("%s failed", name)
        finally:
            conn.close()


def _backup_job():
    import backup
    try:
        log.warning("Backup saved: %s", backup.make_backup())
    except Exception:
        log.exception("Backup failed")


def start(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if not config.RUN_SCHEDULER:
        # The laptop copy sets RUN_SCHEDULER=0 so only the Mac mini sends reminders
        # (two copies with two databases would each email you).
        log.warning("Reminder scheduler is OFF on this computer (RUN_SCHEDULER=0 in .env)")
        return None
    _scheduler = BackgroundScheduler(timezone=config.TZ)
    # On the quarter hour (:00, :15, :30, :45), so the 8:00 digest goes out right at 8:00.
    _scheduler.add_job(_job, "cron", minute="0,15,30,45", args=[app], id="reminders",
                       coalesce=True, max_instances=1, misfire_grace_time=600)
    # Nightly backup at 3:00 AM (database + uploaded documents, last 14 kept). See backup.py.
    _scheduler.add_job(_backup_job, "cron", hour=3, minute=0, id="backup", misfire_grace_time=3600)
    # Discover: look for new postings once a day at 7:05 AM.
    _scheduler.add_job(_sync_job, "cron", hour=7, minute=5, args=[app, "discover"], id="discover",
                       coalesce=True, max_instances=1, misfire_grace_time=3600)
    # Web sweep of company hiring pages: Monday, Wednesday, Friday at 7:20 AM (about 8-10 cents each; Discover page can turn it off).
    _scheduler.add_job(_sync_job, "cron", day_of_week="mon,wed,fri", hour=7, minute=20, args=[app, "sweep"], id="sweep",
                       coalesce=True, max_instances=1, misfire_grace_time=3600)
    # Canvas: every 2 hours from 7 AM to 9 PM (never during quiet hours).
    _scheduler.add_job(_sync_job, "cron", hour="7-21/2", minute=10, args=[app, "canvas"], id="canvas",
                       coalesce=True, max_instances=1, misfire_grace_time=1800)
    # Plus one check shortly after startup, to catch up after the laptop was asleep.
    _scheduler.add_job(_job, "date", run_date=config.now() + timedelta(seconds=20), args=[app], id="startup-check")
    _scheduler.start()
    log.warning("Reminder scheduler started (checks every 15 minutes)")
    return _scheduler
