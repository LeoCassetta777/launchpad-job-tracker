"""Run Launchpad for real (the Mac mini uses this; launchd starts it).

    python serve.py

Same app as `python app.py`, but served by Waitress, a production web server,
instead of Flask's development server (which is meant for coding, not for running
all day). Waitress runs one process with several threads, so the reminder
scheduler runs exactly once. It listens on 127.0.0.1 only; `tailscale serve`
in front of it provides the HTTPS address on your tailnet.
"""
import logging

from waitress import serve

import config
import scheduler
from app import app

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    scheduler.start(app)
    print(f"Launchpad (production) on http://{config.HOST}:{config.PORT}  ·  database: {config.DB_PATH}", flush=True)
    serve(app, host=config.HOST, port=config.PORT, threads=8, ident="Launchpad")
