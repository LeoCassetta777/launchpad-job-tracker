"""Set (or remove) Launchpad's login password. Run it ON THE MAC MINI:

    cd ~/launchpad && .venv/bin/python set_password.py          # set or change the password
    cd ~/launchpad && .venv/bin/python set_password.py --off    # remove the login

You type the password here; it's never shown or stored. Only a scrypt hash goes
into .env (LAUNCHPAD_PASSWORD_HASH). A random LAUNCHPAD_SECRET_KEY (used to sign
the login cookie) is created the first time. Launchpad restarts so it takes effect.
"""
import getpass
import os
import secrets
import subprocess
import sys

from dotenv import dotenv_values, set_key, unset_key
from werkzeug.security import generate_password_hash

import config

ENV = str(config.ENV_PATH)


def restart():
    if sys.platform == "darwin":
        uid = os.getuid()
        result = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{uid}/com.launchpad.app"], capture_output=True)
        print("Launchpad restarted." if result.returncode == 0 else "Restart Launchpad yourself to apply it.")
    else:
        print("Restart Launchpad to apply it.")


if "--off" in sys.argv:
    unset_key(ENV, "LAUNCHPAD_PASSWORD_HASH")
    print("Login removed.")
    restart()
    sys.exit()

password = getpass.getpass("New Launchpad password (at least 10 characters): ")
if len(password) < 10:
    sys.exit("Too short. Use at least 10 characters; a short phrase is easy to remember.")
if getpass.getpass("Type it again: ") != password:
    sys.exit("Those didn't match. Nothing changed.")

# quote_mode="always" keeps the hash's $ signs from being read as variables.
set_key(ENV, "LAUNCHPAD_PASSWORD_HASH", generate_password_hash(password), quote_mode="always")
if not dotenv_values(ENV).get("LAUNCHPAD_SECRET_KEY"):
    set_key(ENV, "LAUNCHPAD_SECRET_KEY", secrets.token_hex(32), quote_mode="never")
print("Password saved (only its hash is stored).")
restart()
