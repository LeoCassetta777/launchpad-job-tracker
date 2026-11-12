# Setting up your own Launchpad

Launchpad is a job-search tracker and weekly planner: a kanban board for internships, jobs,
fellowships, and outreach; contacts; a week planner; AI quick add; fit checks and tailored
resumes; interview prep; reminders by email and phone; a Discover inbox that finds postings
that fit you; Canvas assignments as tasks; and a chat agent that can update everything for you.

**Each person runs their own copy.** Your data stays in a file on your computer, and the AI
features use *your own* Anthropic API key. Nothing is shared with whoever made this, or with
anyone else.

## What you need

- **A computer** running Windows or macOS. A laptop is fine; Launchpad runs while you have it open.
- **Python 3.12 or newer** ([python.org/downloads](https://www.python.org/downloads/)). On Windows, tick “Add python.exe to PATH” in the installer.
- **Git** ([git-scm.com](https://git-scm.com/downloads)).
- **An Anthropic API key** from [console.anthropic.com](https://console.anthropic.com) → API keys. Add a few dollars of credit under Billing. Normal use costs a few dollars a month, and Launchpad has a monthly spending cap (Settings → AI spending; $3 to start).
- Optional:
  - a Gmail account with an app password, for email reminders,
  - the free **ntfy** phone app, for push reminders,
  - your **Canvas** feed links, for assignments and announcements.

## The easy way: let Claude Code set it up

Open Claude Code in the folder where you keep projects (**not** inside OneDrive or iCloud Drive), and paste this:

```text
Set up Launchpad for me from https://github.com/LeoCassetta777/launchpad-job-tracker

1. Clone it into a new "Launchpad" folder here. Check this folder is not inside OneDrive or iCloud Drive (a live database there can get corrupted); if it is, stop and tell me.
2. Create a Python virtual environment in .venv, install requirements.txt, and copy .env.example to .env.
3. Walk me through creating an Anthropic API key and adding it to .env. I'll paste the key into .env myself: never ask me to paste keys or passwords into this chat.
4. Start the app (python app.py) and have me open http://127.0.0.1:5050.
5. Then guide me, one step at a time, through: Settings → Skills profile (help me write it from my resume), Discover → Sources (which career pages to watch), and anything optional I want: Gmail + ntfy reminders (Settings → Reminders) and Canvas links (☰ More → School).

Read README.md and SETUP.md for details. Explain each step in plain English, and tell me what each command does before you run it.
```

## The manual way

**Windows** (PowerShell), in a folder outside OneDrive:

```powershell
git clone https://github.com/LeoCassetta777/launchpad-job-tracker Launchpad
cd Launchpad
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env        # paste your key after ANTHROPIC_API_KEY=, save, close
python app.py
```

**Mac** (Terminal), in a folder outside iCloud Drive:

```bash
git clone https://github.com/LeoCassetta777/launchpad-job-tracker Launchpad
cd Launchpad
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
open -e .env        # paste your key after ANTHROPIC_API_KEY=, save, close
python app.py
```

Open <http://127.0.0.1:5050>. Next time, just activate the environment (second-to-last block of
lines above) and run `python app.py`. Stop it with Ctrl+C.

## First things to do in the app

1. **Settings → Skills profile.** Write a paragraph about your skills, experience, and what you're looking for (role types, fields, locations). Discover, fit checks, and the agent all use it, so this is the most important step.
2. **☰ More → 🔭 Discover → ⚙️ Sources.** Add the career pages you care about (Greenhouse, Lever, or Ashby addresses, or `aisafety.com`). The AI reads every open role and keeps the ones that fit your profile. The 🌐 web sweep (Mon/Wed/Fri, ~8–10¢ each) searches companies' hiring pages more broadly; turn it off there if you don't want it.
3. **Try the 💬 button** (bottom left of the Pipeline page): “I met Sam Lee from Paychex at the career fair, she's a recruiter, follow up Friday.”
4. Optional:
   - **Settings → Reminders:** email (Gmail app password in `.env`) and phone push (ntfy). Instructions are on the page.
   - **☰ More → 🎓 School:** your Canvas Calendar Feed and course announcement feeds.
5. **☰ More → 📖 Guide** explains every feature.

Want to see it full of example data first? Settings → Demo data → Load (and Wipe when you're done).

## Good to know

- **Costs:**
  - Quick add: about a tenth of a cent.
  - Fit check or tailored resume: about 2¢.
  - A chat message: 1–5¢.
  - Discover's daily check: about 1¢; each web sweep: 8–10¢.
  - Settings → AI spending shows what you've used, and the cap stops AI calls at your limit (it asks before going over).
- **Privacy:**
  - Your data (cards, contacts, resumes) is in `data/launchpad.db` on your computer.
  - AI features send the text they work on to Anthropic's API.
  - Canvas feed links work like passwords: keep them to yourself.
- **80,000 Hours:** Launchpad *can* read the 80,000 Hours job board directly (add `80000hours.org` as a career page), but their terms of use don't explicitly allow automated reading. Check with them that it's OK for you, or use their job-alert email instead (subscribe with your Gmail and add `80000hours.org` as an alert sender).
- **LinkedIn and Indeed** forbid automated reading, so Launchpad doesn't load their sites. Use their job-alert emails (add `linkedin.com` / `indeed.com` as senders) or rely on the web sweep.
- **Updates:** `git pull` in the Launchpad folder, then restart. Your data and `.env` are never touched.
- **Want it running all the time** (reminders while your laptop is closed, access from your phone)? See README.md → “Optional: running it on an always-on Mac”.
