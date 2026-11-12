"""Nightly backups: a zip of the database plus your uploaded documents. Keeps 14 days.

    python backup.py      make one now (also runs by itself at 3:00 AM; see scheduler.py)

The database is copied with SQLite's own backup feature, which takes a consistent
snapshot even while the app is running (copying the .db file directly could catch
it mid-write). Backups go in DATA_DIR/backups as launchpad-YYYY-MM-DD.zip.
To restore: stop Launchpad, unzip, put launchpad.db (and documents/) back in DATA_DIR.
"""
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import config

KEEP = 14


def backup_dir():
    path = config.DATA_DIR / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_backup():
    """Create today's backup (replacing one made earlier today) and delete ones older than 14."""
    target = backup_dir() / f"launchpad-{config.today_str()}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "launchpad.db"
        src = sqlite3.connect(config.DB_PATH)
        dst = sqlite3.connect(snapshot)
        with dst:
            src.backup(dst)               # consistent copy, safe while the app runs
        src.close()
        dst.close()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, "launchpad.db")
            docs = config.DATA_DIR / "documents"
            if docs.is_dir():
                for f in docs.iterdir():
                    if f.is_file():
                        z.write(f, f"documents/{f.name}")
    for old in sorted(backup_dir().glob("launchpad-*.zip"))[:-KEEP]:
        old.unlink()
    return target


if __name__ == "__main__":
    path = make_backup()
    print(f"Backup saved: {path} ({path.stat().st_size / 1024:.0f} KB)")
