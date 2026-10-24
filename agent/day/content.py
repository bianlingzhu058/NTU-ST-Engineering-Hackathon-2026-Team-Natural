"""What the bot writes: to do lines, notes, sheet rows and list notes, drawn fresh every run.

Nothing here is a fixed script. Every text is built from small word banks with random picks, so
two runs never type the same document. Sentences come with a second wording where it makes sense,
which the rewrite attempt can use. Item wordings live in config/workday.yaml so a range operator
can change them without touching code.
"""
from datetime import datetime
import random

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PEOPLE = ["sarah", "tom", "priya", "wei ming", "jason", "nurul", "mei", "daniel", "aisha", "ken"]
TEAMS = ["design", "finance", "ops", "the vendor", "marketing", "IT", "the client", "sales"]
TOPICS = ["the laptop order", "the q4 budget", "the training plan", "the office move", "the new hires",
          "the client demo", "the server costs", "the travel claims", "the team offsite", "the website update"]
WHEN = ["by friday", "next week", "before the 30th", "on monday", "end of the month", "tomorrow"]


def today(fmt: str = "{d} {mon}", when: datetime | None = None) -> str:
    """'24 oct' style date, lower case like a quick note."""
    when = when or datetime.now()
    return fmt.format(d=when.day, mon=MONTHS[when.month - 1], day=DAYS[when.weekday()], Mon=MONTHS[when.month - 1].title())


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def note_sentences(rng: random.Random, kind: str, label: str = "") -> tuple[str, list[tuple[str, str]], list[str]]:
    """(title, [(sentence, alternative wording)], extra sentences that may be parked and deleted).
    The to do line decides the subject: 'draft email to tom' writes to tom, 'plan for the offsite'
    plans the offsite."""
    p1, p2 = rng.sample(PEOPLE, 2)
    named = [p for p in PEOPLE if p in label]
    if named:
        p1 = named[0]
        p2 = rng.choice([p for p in PEOPLE if p != p1])
    team, topic, when = rng.choice(TEAMS), rng.choice(TOPICS), rng.choice(WHEN)
    for t in TEAMS:
        if f"the {t} meeting" in label or f" {t} " in f" {label} ": team = t
    if kind == "plan" and label.startswith(("plan for ", "rough plan for ")):
        topic = "the " + label.split(" for ", 1)[1].replace("the ", "")
    n = rng.randint(2, 6)
    pool = {
        "meeting": [
            (f"Met with {team} about {topic}.", f"Short meeting with {team} on {topic}."),
            (f"{_cap(p1)} will send the updated numbers {when}.", f"{_cap(p1)} sends the new numbers {when}."),
            (f"We agreed to keep it small for now and check again {rng.choice(WHEN)}.", ""),
            (f"Open question is who signs off on the costs.", f"Still open: who signs off on the costs."),
            (f"{_cap(p2)} asked for a short summary by email.", ""),
            (f"Next meeting is {rng.choice(DAYS)} at {rng.randint(9, 16)}.", f"We meet again on {rng.choice(DAYS)}."),
            (f"Need to follow up with {p1} about {n} open items.", ""),
        ],
        "update": [
            (f"This week I mostly worked on {topic}.", f"Most of this week went into {topic}."),
            (f"The {rng.choice(['draft', 'first version', 'plan'])} is done and sent to {p1}.", ""),
            (f"Waiting on {team} for the final numbers.", f"Still waiting for {team} to send the final numbers."),
            (f"Next week I will start on {rng.choice(TOPICS)}.", ""),
            (f"No big blockers, only {p2} is away {rng.choice(['on monday', 'for two days', 'next week'])}.", ""),
            (f"Spent about {rng.randint(2, 6)} hours on emails and calls.", ""),
        ],
        "email": [
            (f"Hi {p1}, quick note on {topic}.", f"Hi {p1}, just a short update on {topic}."),
            (f"I checked the numbers and they look fine to me.", f"The numbers look ok from my side."),
            (f"Can you send me the final list {when}?", ""),
            (f"Let me know if {team} needs anything else.", ""),
            (f"Thanks, talk soon.", ""),
        ],
        "plan": [
            (f"Plan for {topic}.", ""),
            (f"First get the costs from {team}.", f"Start by asking {team} for the costs."),
            (f"Then check with {p1} if the dates still work.", ""),
            (f"Budget stays under {rng.choice([2, 3, 5, 8, 12])} thousand for now.", ""),
            (f"Decide {when}.", ""),
        ],
    }[kind]
    keep = [pool[0]] + rng.sample(pool[1:], k=min(len(pool) - 1, rng.randint(2, 4)))
    title = {"meeting": f"meeting notes {today()}", "update": f"weekly update {today()}",
             "email": f"email to {p1}", "plan": f"plan for {topic.replace('the ', '')}"}[kind]
    extras = [f"Maybe ask {p2} about the old invoices.", f"Check the shared folder later.",
              f"Remember the {rng.choice(['call', 'demo', 'review'])} at {rng.randint(2, 5)}."]
    return title, keep, extras


SHEETS = {
    "budget": (["Item", "Cost", "Qty"], ["Monitor", "Keyboard", "Dock", "Webcam", "Chair", "Headset", "Laptop stand",
                                         "Printer ink", "Cables", "Desk lamp", "USB drive", "Mouse"], (15, 450), (1, 8)),
    "expenses": (["Date", "What", "Amount"], ["Taxi", "Lunch with client", "Parking", "Train", "Coffee", "Hotel",
                                              "Printing", "Courier", "Team dinner", "Flight"], (6, 380), None),
    "timesheet": (["Day", "Project", "Hours"], ["Website", "Budget review", "Client demo", "Training", "Admin",
                                               "Vendor calls", "Reports"], (1, 8), None),
}


def no_prefix_clash(labels: list[str]) -> list[str]:
    """Calc AutoInput completes a label that starts like an earlier one in the column: drop those."""
    out = []
    for label in labels:
        low = label.lower()
        if any(low.startswith(o.lower()) or o.lower().startswith(low) for o in out): continue
        out.append(label)
    return out


def sheet_rows(rng: random.Random, kind: str, n: int, used: set[str] | None = None) -> tuple[list[str], list[list[str]]]:
    headers, labels, (lo, hi), qty = SHEETS[kind]
    used = {u.lower() for u in (used or set())}
    pool = no_prefix_clash([l for l in rng.sample(labels, len(labels))
                            if not any(l.lower().startswith(u) or u.startswith(l.lower()) for u in used)])
    rows = []
    for label in pool[:n]:
        if kind == "expenses":
            rows.append([f"{rng.randint(1, 28)}/{datetime.now().month}", label, f"{rng.uniform(lo, hi):.2f}"])
        elif kind == "timesheet":
            rows.append([rng.choice(DAYS).title(), label, str(rng.randint(lo, hi))])
        else:
            rows.append([label, str(rng.randint(lo, hi)), str(rng.randint(*qty))])
    return headers, rows


# Writer AutoCorrect rewrites some strings and changes their length (dont -> don't, 1/2 -> a
# fraction sign), which would put the bot's copy of the page out of step. Keep them out of the banks.
DONE_NOTES = ["done", "done", "finished", "ok"]
FAIL_NOTES = ["{site} page down, try later", "{site} not loading, try again later", "could not open {site}, later"]
SAVED_NOTE = ["saved in {file}", "in {file}", "notes in {file}", "see {file}"]
PROGRESS = ["{done} of {total} done, rest tbc", "{done} out of {total} done, rest tomorrow", "done {done} of {total}, rest tbc"]


# Notes built from what a page really shows (config/page_facts.json, captured from the VM dumps).
# Each recipe returns (title, [(sentence, second wording)], extras) like note_sentences.

def _pick(rng, items, k):
    items = list(items)
    return rng.sample(items, min(k, len(items)))


def news_note(rng, facts, label):
    sites = [s for s in ("apnews", "bbc") if s in facts]
    picks = []
    for site in sites:
        for h in _pick(rng, facts[site]["headlines"], rng.randint(1, 2)):
            picks.append((site, h.rstrip(".") if h[-1:] not in "?!" else h))
    name = {"apnews": "AP", "bbc": "BBC"}
    sentences = [(f"Quick news round up for the team, {today()}.", f"News notes for the team, {today()}.")]
    for site, h in picks:
        end = "" if h[-1:] in "?!" else "."
        sentences.append((f"{name[site]}: {h}{end}", f"From {name[site]}: {h}{end}"))
    shared = [w for w in ("World Cup", "NATO", "Iran", "Trump") if all(any(w in h for h in facts[s]["headlines"]) for s in sites)]
    if shared:
        topic = rng.choice(shared)
        sentences.append((f"Both AP and BBC lead with {topic} today.", f"{topic} is on both AP and BBC."))
    sentences.append((rng.choice(["Nothing that changes our plans.", "Worth a read at lunch.", "Will share the links in the chat."]), ""))
    return f"news notes {today()}", sentences, ["Check the business pages later."]


def training_note(rng, facts, label):
    person = next((p for p in PEOPLE if p in label), rng.choice(PEOPLE)).title()
    courses = _pick(rng, facts["coursera"]["courses"], rng.randint(2, 3))
    s = [(f"Training ideas for {person}.", f"Course ideas for {person}.")]
    for c in courses:
        why = rng.choice(["good start", "useful for the reports", "for the data work", "if there is time"])
        s.append((f"{c}, {why}.", ""))
    s.append((f"Coursera says {facts['coursera']['offer']}.", f"There is a deal: {facts['coursera']['offer']}."))
    s.append((f"Ask {person} which one first.", f"Let {person} pick one."))
    return f"training ideas {person.lower()}", s, [f"Also look at {rng.choice(facts['coursera']['courses'])}."]


def cloud_note(rng, facts, label):
    a, g = _pick(rng, facts["aws"]["points"], 2), _pick(rng, facts["googlecloud"]["points"], 2)
    s = [("Cloud options, quick look.", "Quick comparison of the two clouds."),
         (f"AWS: {a[0]}.", ""), (f"AWS also has {a[1]}.", ""),
         (f"Google Cloud: {g[0]}.", ""), (f"Google also gives {g[1]}.", ""),
         (rng.choice(["The free credit makes Google easier to try first.", "AWS looks bigger, Google cheaper to start."]),
          "Google is easier to try for free.")]
    s = [s[0]] + [x for i, x in enumerate(s[1:5]) if i in (0, 2) or rng.random() < 0.5] + [s[5]]
    return f"cloud options {today()}", s, ["Ask IT what we use now."]


def phone_note(rng, facts, label):
    person = next((p for p in PEOPLE if p in label), rng.choice(PEOPLE)).title()
    models = _pick(rng, facts["samsung"]["models"], rng.randint(2, 3))
    s = [(f"Phone options for {person}.", f"Samsung options for {person}.")]
    s += [(f"{m}, on the samsung homepage.", "") for m in models]
    s.append(("No prices on the homepage, ask the shop.", "Prices not shown online, check in store."))
    return f"phone options {person.lower()}", s, [f"{facts['samsung']['note']}."]


def asana_note(rng, facts, label):
    pts = _pick(rng, facts["asana"]["points"], rng.randint(2, 3))
    s = [("Asana for the team tasks?", "Notes on Asana for our tasks.")]
    s += [(f"They have {p}.", "") for p in pts]
    s.append((rng.choice(["Could replace the shared sheet.", "Maybe try it with two people first."]), ""))
    return f"asana notes {today()}", s, ["Check the price later."]


RECIPES = {"news": news_note, "training": training_note, "cloud": cloud_note, "phone": phone_note, "asana": asana_note}
