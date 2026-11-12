"""Fill the app with fake demo data, or wipe it again.

    python seed.py          add demo opportunities, tasks, contacts (dates relative to today)
    python seed.py --wipe   remove ONLY the demo rows; your real data is untouched
    python seed.py --reset  wipe the demo rows, then add fresh ones

Every demo row has is_seed = 1, which is how --wipe knows what to delete.
All companies and people here are made up.
"""
import sys
from datetime import timedelta

import config
from db import connect, init_db, log_activity

def day(offset):
    """A date `offset` days from today, as text."""
    return (config.now().date() + timedelta(days=offset)).isoformat()


def weekday(n):
    """Monday=0 ... Sunday=6 of THIS week, as text."""
    today = config.now().date()
    return (today - timedelta(days=today.weekday()) + timedelta(days=n)).isoformat()


def demo_data():
    """Build the demo rows. A function (not module-level lists) so dates are
    relative to the day you run it, even if the server has been up for days."""
    CONTACTS = [
        # key, name, company, role, email, how_met, follow_up offset, notes
        ("maya", "Maya Okafor", "Copperline Security", "Security Engineering Manager", "maya.okafor@example.com",
         "Golisano networking night", -1, "Runs the AppSec team. Suggested I look at their spring internship."),
        ("dev", "Dev Patel", "Finch & Fern Labs", "Data Scientist", "dev.patel@example.com",
         "Alumni referral from a classmate", 3, "Happy to refer me once a posting opens."),
        ("rosa", "Rosa Lindqvist", "Lanternfly Fellowship", "Program Coordinator", "rosa@example.org",
         "Info session (virtual)", None, "Said they read every essay. Answer the 'why now' question directly."),
        ("ben", "Ben Achterberg", "Harborlight Credit Union", "IT Director", "ben.a@example.com",
         "Cold email", 0, "Replied fast. Interested in AI policy help for a small IT team."),
        ("jules", "Jules Moreau", "Bluepeak Health", "Talent Acquisition", "jules.moreau@example.com",
         "LinkedIn", 7, ""),
        ("sam", "Sam Whitford", "Kettle Street Ventures", "Associate", "sam@example.com",
         "Met at Rochester startup meetup", -5, "Knows a lot of local founders. Follow up about intro to Copperline."),
        ("ana", "Ana Ruiz", "Copperline Security", "Recruiter", "ana.ruiz@example.com",
         "Maya introduced us", None, ""),
        ("theo", "Theo Grant", "Silo Nine Robotics", "Founder", "theo@example.com",
         "Startup pitch night", 10, "Small team, might create a role if I bring a concrete project idea."),
    ]

    OPPORTUNITIES = [
        # key, fields
        ("copper", dict(type="internship", company="Copperline Security", title="AppSec Intern (Spring)",
                        link="https://example.com/copperline/appsec-intern", source="referral", location="Rochester, NY (hybrid)",
                        pay="$24/hr", stage="talking", urgency="pressing", importance="high", deadline=day(9),
                        next_action="Prep for second-round call", next_action_date=day(1),
                        notes="First call went well. They care about threat modeling.", tags="ai,security")),
        ("lantern", dict(type="fellowship", company="Lanternfly Fellowship", title="AI for Public Good Fellow",
                         link="https://example.org/lanternfly", source="company_site", location="Remote",
                         stage="preparing", urgency="on_fire", importance="high", deadline=day(4), deadline_time="23:59",
                         next_action="Finish required course 2", next_action_date=day(0),
                         notes="Two required online courses before the application unlocks.", tags="ai,fellowship")),
        ("finch", dict(type="job", company="Finch & Fern Labs", title="Junior Data Analyst",
                       link="https://example.com/finchfern/careers", source="linkedin", location="Buffalo, NY",
                       pay="$58–65k", stage="sent", urgency="soon", importance="medium", deadline=None,
                       next_action="Ask Dev to flag my application", next_action_date=day(2),
                       notes="Applied with Resume – Data v2.", tags="data,python")),
        ("harbor", dict(type="outreach", company="Harborlight Credit Union", title="AI policy help (informal)",
                        source="cold_outreach", location="Rochester, NY", stage="talking", urgency="soon",
                        importance="medium", next_action="Send 1-page proposal", next_action_date=day(3),
                        notes="They want an acceptable-use policy for AI tools.", tags="ai,security")),
        ("bluepeak", dict(type="internship", company="Bluepeak Health", title="Product Analytics Intern",
                          link="https://example.com/bluepeak/jobs/123", source="12twenty", location="Remote",
                          stage="waiting", urgency="chill", importance="medium",
                          next_action="Follow up with Jules if no reply", next_action_date=day(-2),
                          notes="Applied 10 days ago.", tags="data")),
        ("silo", dict(type="outreach", company="Silo Nine Robotics", title="Possible project role",
                      source="other", location="Rochester, NY", stage="interested", urgency="chill",
                      importance="medium", next_action="Draft a project idea for Theo", next_action_date=day(6),
                      tags="robotics,ai")),
        ("kettle", dict(type="outreach", company="Kettle Street Ventures", title="Coffee chat / intros",
                        source="referral", location="Rochester, NY", stage="sent", urgency="soon", importance="low",
                        next_action="", tags="networking")),
        ("orchard", dict(type="job", company="Orchard Lane Software", title="Associate Product Manager",
                         link="https://example.com/orchard/apm", source="linkedin", location="Remote",
                         stage="interested", urgency="soon", importance="high", deadline=day(12),
                         next_action="Tailor resume for APM", next_action_date=day(2), tags="product")),
        ("riverbend", dict(type="fellowship", company="Riverbend Civic Fellowship", title="Summer Fellow",
                           source="company_site", location="Albany, NY", stage="offer", urgency="pressing",
                           importance="medium", deadline=day(5), next_action="Decide by Friday",
                           next_action_date=day(5), notes="Offer received! Stipend $6k.", tags="fellowship,policy")),
        ("glassworks", dict(type="internship", company="Glassworks Media", title="Marketing Analytics Intern",
                            source="12twenty", location="Rochester, NY", stage="closed", close_reason="rejected",
                            urgency="chill", importance="low", tags="marketing")),
        ("tidal", dict(type="job", company="Tidal Byte", title="IT Support Associate", source="other",
                       location="Buffalo, NY", stage="closed", close_reason="ghosted", urgency="chill",
                       importance="low")),
    ]

    LINKS = [("copper", "maya"), ("copper", "ana"), ("finch", "dev"), ("lantern", "rosa"), ("harbor", "ben"),
             ("bluepeak", "jules"), ("kettle", "sam"), ("silo", "theo"), ("copper", "sam")]

    INTERACTIONS = [
        # contact, opportunity, kind, days ago, note
        ("maya", "copper", "event", 30, "Met at networking night, talked threat modeling."),
        ("maya", "copper", "emailed", 21, "Thank-you note + asked about internships."),
        ("maya", "copper", "replied", 19, "Introduced me to Ana."),
        ("ana", "copper", "call", 6, "First-round call. 30 min. Went well."),
        ("dev", "finch", "coffee", 12, "Coffee at the library café."),
        ("rosa", "lantern", "event", 9, "Asked about the course requirement."),
        ("ben", "harbor", "emailed", 8, "Cold email about AI policy help."),
        ("ben", "harbor", "replied", 5, "Interested! Wants a short proposal."),
        ("jules", "bluepeak", "linkedin", 15, "Connected and mentioned my application."),
        ("sam", "kettle", "event", 25, "Startup meetup."),
        ("theo", "silo", "event", 3, "Pitch night. Hiring 'eventually'."),
    ]

    TASKS = [
        # Each dict is one task. Dates spread across this week so every view has something.
        dict(title="Finish Lanternfly required course 2", opp="lantern", planned_date=day(0), due_date=day(2),
             urgency="on_fire", importance="high", est_min=120, energy="high",
             checklist=[("Module 1", 1), ("Module 2", 1), ("Module 3", 0), ("Final quiz", 0)]),
        dict(title="Second-round call with Copperline", opp="copper", contact="ana", planned_date=day(1),
             start_time="14:00", duration_min=45, urgency="pressing", importance="high", est_min=45, energy="high"),
        dict(title="Prep STAR stories for Copperline", opp="copper", planned_date=day(0), urgency="pressing",
             importance="high", est_min=60, energy="med"),
        dict(title="Finance homework (problem set 6)", planned_date=weekday(3), due_date=weekday(3),
             urgency="soon", importance="medium", est_min=120, energy="high", repeat="weekly"),
        dict(title="Email 3 local companies about AI security", planned_date=weekday(2), urgency="soon",
             importance="high", est_min=90, energy="med",
             checklist=[("Pick 3 companies", 1), ("Draft template", 0), ("Send all 3", 0)]),
        dict(title="Write Harborlight 1-page proposal", opp="harbor", contact="ben", due_date=day(3),
             urgency="soon", importance="medium", est_min=90, energy="high"),
        dict(title="Follow up with Jules at Bluepeak", opp="bluepeak", contact="jules", planned_date=day(-2),
             urgency="soon", importance="medium", est_min=15, energy="low"),
        dict(title="Update LinkedIn headline", urgency="chill", importance="low", est_min=20, energy="low"),
        dict(title="Read 'threat modeling' chapter", urgency="chill", importance="medium", est_min=45, energy="med"),
        dict(title="Coffee chat with Sam", opp="kettle", contact="sam", planned_date=weekday(4), start_time="10:30",
             duration_min=30, urgency="chill", importance="medium", est_min=30, energy="med"),
        dict(title="Weekly 12Twenty check", planned_date=weekday(0), urgency="chill", importance="medium",
             est_min=20, energy="low", repeat="weekly", status="done"),
        dict(title="Tailor resume for Orchard APM", opp="orchard", planned_date=day(2), urgency="soon",
             importance="high", est_min=60, energy="med"),
    ]
    return CONTACTS, OPPORTUNITIES, LINKS, INTERACTIONS, TASKS


DEMO_RESUME = """Alex Demo — Rochester, NY — alex.demo@example.com
Education: Golisano Institute, B.S. Business & Entrepreneurship (expected 2027)
Skills: Python (pandas), SQL (PostgreSQL), n8n automations, Excel, basic Tableau
Experience:
- Operations Intern, Lakeview Coffee Co. (Summer 2026): automated weekly inventory reports with Python and n8n, cutting 3 hours of manual work per week.
- Student Analyst, campus startup studio: built SQL dashboards tracking 40 student ventures.
Projects: AI policy brief for a local credit union; vending-machine sales agent using an LLM API.
"""

# (opportunity key or None, kind, question, my answer, tags, 1 = best answer)
DEMO_QUESTIONS = [
    ("copper", "asked", "Tell me about a time you automated something tedious.",
     "At Lakeview Coffee I automated the weekly inventory report with Python and n8n. It saved about 3 hours a week "
     "and removed copy-paste errors.", "behavioral", 1),
    ("copper", "asked", "How would you explain threat modeling to a non-technical manager?", "", "technical,about_ai", 0),
    ("copper", "to_ask", "What does a great first 90 days look like for this intern?", "", "company", 0),
    (None, "bank", "Why do you want to work in AI security?",
     "I've built small AI tools and seen how easily they leak data or get misused. I want to be the person who makes "
     "them safe to use.", "about_me,about_ai", 1),
]

# (opportunity key, reason, stage it reached, days it was open, lesson)
DEMO_REJECTIONS = [
    ("glassworks", "rejected", "sent", 21, "Applied with my generic resume. Tailor the summary to marketing next time."),
    ("tidal", "ghosted", "waiting", 30, ""),
]


def has_seed_data(conn):
    return conn.execute("SELECT COUNT(*) FROM opportunities WHERE is_seed = 1").fetchone()[0] > 0


def wipe(conn):
    for table in ("questions", "rejections", "tasks", "opportunities", "contacts", "documents", "activity_log"):
        n = conn.execute(f"DELETE FROM {table} WHERE is_seed = 1").rowcount
        print(f"  removed {n} demo rows from {table}")
    conn.commit()


def seed(conn):
    CONTACTS, OPPORTUNITIES, LINKS, INTERACTIONS, TASKS = demo_data()
    now = config.now_str()
    contact_ids, opp_ids = {}, {}

    for key, name, company, role, email, how_met, fu, notes in CONTACTS:
        cur = conn.execute(
            """INSERT INTO contacts (name, company, role, email, how_met, follow_up_date, notes, is_seed, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (name, company, role, email, how_met, day(fu) if fu is not None else None, notes, now, now))
        contact_ids[key] = cur.lastrowid
        log_activity(conn, "contact", cur.lastrowid, "created", f"Added contact: {name}", is_seed=1)

    for position, (key, fields) in enumerate(OPPORTUNITIES):
        fields = {**fields, "position": position, "is_seed": 1, "created_at": now, "updated_at": now}
        cols = ", ".join(fields)
        cur = conn.execute(f"INSERT INTO opportunities ({cols}) VALUES ({', '.join('?' for _ in fields)})",
                           list(fields.values()))
        opp_ids[key] = cur.lastrowid
        log_activity(conn, "opportunity", cur.lastrowid, "created", f"Added {fields['company']}", is_seed=1)

    for opp, contact in LINKS:
        conn.execute("INSERT INTO opportunity_contacts VALUES (?, ?)", (opp_ids[opp], contact_ids[contact]))

    for contact, opp, kind, ago, note in INTERACTIONS:
        conn.execute(
            """INSERT INTO interactions (contact_id, opportunity_id, kind, happened_on, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""", (contact_ids[contact], opp_ids[opp], kind, day(-ago), note, now))

    # Opportunity checklist: the fellowship's required steps.
    for pos, (text, done) in enumerate([("Finish required course 1", 1), ("Finish required course 2", 0),
                                        ("Write personal essay", 0), ("Submit application", 0)]):
        conn.execute("INSERT INTO checklist_items (opportunity_id, text, done, position, created_at) VALUES (?, ?, ?, ?, ?)",
                     (opp_ids["lantern"], text, done, pos, now))

    for t in TASKS:
        t = dict(t)
        checklist = t.pop("checklist", [])
        t["opportunity_id"] = opp_ids.get(t.pop("opp", None))
        t["contact_id"] = contact_ids.get(t.pop("contact", None))
        t.update(is_seed=1, created_at=now, updated_at=now)
        if t.get("status") == "done":
            t["completed_at"] = now
        cols = ", ".join(t)
        cur = conn.execute(f"INSERT INTO tasks ({cols}) VALUES ({', '.join('?' for _ in t)})", list(t.values()))
        for pos, (text, done) in enumerate(checklist):
            conn.execute("INSERT INTO checklist_items (task_id, text, done, position, created_at) VALUES (?, ?, ?, ?, ?)",
                         (cur.lastrowid, text, done, pos, now))
        log_activity(conn, "task", cur.lastrowid, "created", f"Added task: {t['title']}", is_seed=1)

    # Phase 4 demo rows: a resume (text only, no file), interview questions, rejection lessons.
    cur = conn.execute(
        "INSERT INTO documents (kind, label, text, notes, is_seed, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
        ("resume", "Resume – Data v2 (demo)", DEMO_RESUME, "Fake demo resume", now, now))
    resume_id = cur.lastrowid
    conn.execute("INSERT INTO opportunity_documents (opportunity_id, document_id, sent_on, created_at) VALUES (?, ?, ?, ?)",
                 (opp_ids["finch"], resume_id, day(-9), now))
    for opp, kind, text, answer, tags, best in DEMO_QUESTIONS:
        conn.execute("INSERT INTO questions (opportunity_id, kind, text, answer, tags, best, is_seed, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)", (opp_ids.get(opp), kind, text, answer, tags, best, now, now))
    for opp, reason, stage, days_open, lesson in DEMO_REJECTIONS:
        o = next(f for k, f in OPPORTUNITIES if k == opp)
        conn.execute("INSERT INTO rejections (opportunity_id, company, title, type, source, reason, stage_reached, "
                     "days_open, lesson, is_seed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                     (opp_ids[opp], o["company"], o.get("title", ""), o["type"], o["source"], reason, stage,
                      days_open, lesson, f"{day(-days_open // 3)} 10:00:00"))

    conn.commit()
    print(f"  added {len(OPPORTUNITIES)} opportunities, {len(TASKS)} tasks, {len(CONTACTS)} contacts, "
          f"{len(INTERACTIONS)} interactions")


if __name__ == "__main__":
    init_db()
    conn = connect()
    args = sys.argv[1:]
    if "--wipe" in args or "--reset" in args:
        print("Wiping demo data…")
        wipe(conn)
    if "--wipe" not in args:
        if has_seed_data(conn):
            print("Demo data is already there. Use --reset to replace it, or --wipe to remove it.")
        else:
            print("Adding demo data…")
            seed(conn)
    conn.close()
    print(f"Done. Database: {config.DB_PATH}")
