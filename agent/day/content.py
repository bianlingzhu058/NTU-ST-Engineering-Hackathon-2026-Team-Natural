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


# Notes built from what the bot just read on the page (agent/day/eyes.py), never from stored text.
# A note is a short title, one line per item taken off the page (copied or typed), a closing line or
# two, and a follow up that goes onto the to do list (Kellyn, 25 Oct). The title says the topic once;
# no first line repeats it. A recipe returns None when the page did not give enough to write about.
# Each recipe returns (title, [(sentence, second wording)], extras) like note_sentences.

def _pick(rng, items, k):
    items = list(items)
    return rng.sample(items, min(k, len(items)))


def _say(rng, *options):
    return rng.choice(options)


def news_note(rng, facts, label):
    sites = [s for s in ("apnews", "bbc") if facts.get(s, {}).get("headlines")]
    if not sites: return None
    name = {"apnews": "AP", "bbc": "BBC"}
    items = []
    for site in sites:
        for h in _pick(rng, facts[site]["headlines"], rng.randint(1, 2)):
            items.append({"text": h.rstrip("."), "copy": h, "site": site, "prefix": f"{name[site]}: "})
    outro = []
    shared = [w for w in ("World Cup", "NATO", "Iran") if all(any(w in h for h in facts[s]["headlines"]) for s in sites)]
    if len(sites) > 1 and shared:
        t = rng.choice(shared)
        outro.append((f"Both AP and BBC lead with {t} today.", f"{t} is on both AP and BBC."))
    outro.append((_say(rng, "Nothing that changes our plans.", "Worth a read at lunch."), ""))
    return {"title": f"news notes {today()}", "items": items, "outro": outro,
            "extras": ["Check the business pages later."],
            "followup": _say(rng, "send the news links to the team", "share news notes in the chat")}


def training_note(rng, facts, label):
    c = facts.get("coursera", {})
    if len(c.get("courses", [])) < 2: return None
    person = next((p for p in PEOPLE if p in label), rng.choice(PEOPLE))
    items = [{"text": x, "copy": x} for x in _pick(rng, c["courses"], rng.randint(2, 3))]
    outro = [(f"{c['offer'][:1].upper() + c['offer'][1:]}.", "")] if c.get("offer") else []
    outro.append((_say(rng, "All on Coursera, no exam needed.", "All online, can start anytime."), ""))
    return {"title": f"Training ideas for {person.title()}", "items": items, "outro": outro,
            "extras": [f"Also look at {rng.choice(c['courses'])}."],
            "followup": _say(rng, f"ask {person} which course first", f"check course budget for {person}")}


def cloud_note(rng, facts, label):
    a, g = facts.get("aws", {}).get("points", []), facts.get("googlecloud", {}).get("points", [])
    if not a and not g: return None                         # one cloud is enough to write something
    items = [{"text": f"AWS: {p}", "copy": p, "prefix": "AWS: "} for p in _pick(rng, a, min(2, len(a)))]
    items += [{"text": f"Google: {p}", "copy": p, "prefix": "Google: "} for p in _pick(rng, g, min(2, len(g)))]
    if a and g:
        outro = [(_say(rng, "Free credit makes Google easier to try first.", "AWS is bigger, Google cheaper to start."),
                  "Google is easier to try for free.")]
    else:
        outro = [(_say(rng, "Only got one side today, compare again later.", "Other site was down, check again."), "")]
    return {"title": f"Cloud options {today()}", "items": items, "outro": outro, "extras": ["Ask IT what we use now."],
            "followup": _say(rng, "ask IT about cloud costs", "check what IT uses now")}


def phone_note(rng, facts, label):
    """Phones read off the Samsung homepage. One phone is still a note, and the list says that only that one
    was there ("only the Galaxy Z Fold7 so far"), then tbc (Kellyn, 25 Oct)."""
    sm = facts.get("samsung", {})
    models = sm.get("models", [])
    if not models: return None
    person = next((p for p in PEOPLE if p in label), rng.choice(PEOPLE))
    items = [{"text": m, "copy": m} for m in _pick(rng, models, min(len(models), rng.randint(2, 3)))]
    outro = [(_say(rng, "All on the Samsung homepage, no prices shown.", "On the homepage, but no prices."), "")]
    if sm.get("pre_registration"):
        outro.insert(0, (_say(rng, "Pre-registration is open for a new Galaxy.", "A new Galaxy is up for pre-registration."), ""))
    made = {"title": f"Phone options for {person.title()}", "items": items, "outro": outro,
            "extras": ["Check the trade in deal."],
            "followup": _say(rng, "call samsung, which phone is cheapest", f"ask {person} which phone")}
    if len(models) == 1:
        made["partial"] = _say(rng, f"only the {models[0]} so far", f"only {models[0]} on samsung so far")
    return made


def asana_note(rng, facts, label):
    pts = facts.get("asana", {}).get("points", [])
    if len(pts) < 2: return None
    items = [{"text": p, "copy": p} for p in _pick(rng, pts, rng.randint(2, 3))]
    outro = [(_say(rng, "Could replace our shared sheet.", "Maybe try it with two people first."), "")]
    return {"title": "Asana for the team?", "items": items, "outro": outro, "extras": ["Check the price later."],
            "followup": _say(rng, "show asana to the team", "ask about asana price")}


RECIPES = {"news": news_note, "training": training_note, "cloud": cloud_note, "phone": phone_note, "asana": asana_note}


# What goes on the to do list after a task, chosen from what really happened (the task's record).
# The wording varies a little, the meaning never does.
OUTCOME = {
    "done": ["done", "done", "finished", "ok"],
    "links_error": ["done but some pages error", "done, but some links did not open", "done, a few pages error"],
    "site_error": ["{site} page error, try again later", "page error, try again later", "{site} not loading, try again later"],
    "missing": ["{site} shows no {what}, try later", "no {what} on {site} today, try later"],
    "goal_down": ["{site} {what} page down, try again later", "{what} page not opening, try again later"],
    "missing_started": ["{site} shows no {what} yet, started in {file}", "no {what} on {site} yet, started in {file}"],
    "one_site_error": ["done, {site} page error", "done, {site} was down"],
    "saved": ["saved in {file}", "in {file}", "see {file}"],
    "cut": ["started"],
}


def outcome_note(rng, key: str, **kw) -> str:
    return rng.choice(OUTCOME[key]).format(**kw)


def linked_note(rng, link, label: str):
    """An office note that grows out of the day's hybrid task ("send crypto summary to tom"), written
    using what that task really found (link.found). If it found nothing, the note says so."""
    person = next((p for p in PEOPLE if p in label), rng.choice(PEOPLE))
    found = getattr(link, "found", None) or {}
    facts, kind, file = found.get("facts", []), found.get("kind", ""), found.get("file", "")
    hi = _say(rng, f"Hi {person.title()},", f"Hi {person.title()}, quick update.")
    s = [(hi, "")]
    spec = getattr(link, "spec", {}) or {}
    kind = kind or {"crypto_prices": "crypto", "crypto_compare": "fx"}.get(spec.get("task"), spec.get("recipe", ""))
    topic = {"crypto": "crypto summary", "fx": "crypto rates", "news": "news summary", "training": "course list",
             "phone": "phone shortlist", "cloud": "cloud summary", "asana": "asana summary"}.get(kind, "update")
    title = f"{topic} {person}"                          # a clean title and file name (no typo from the list)
    if not facts:                                         # say what really happened to the source task
        if getattr(link, "status", "") == "failed":
            s.append((_say(rng, "The site was down when I checked today, will send it tomorrow.",
                           "Could not get it today, the page was not working."), ""))
        else:
            s.append((_say(rng, "Not finished yet, will send it later.", "Still working on it, more tomorrow."), ""))
        return title, s, []
    if kind == "crypto":
        for name, price, cap in facts[:3]:
            s.append((f"{name} is at US${price} today.", f"{name} is US${price} on CoinGecko."))
    elif kind == "fx":
        for coin, usd, sgd in facts[:3]:
            s.append((f"{coin} is US${usd}" + (f", S${sgd} on Coinbase." if sgd else ", no SGD price yet."), ""))
    else:
        for line in facts[:3]:
            s.append((line.rstrip(".") + ".", ""))
    if file:
        s.append((_say(rng, f"Details are in {file}.", f"It is all in {file}."), ""))
    s.append((_say(rng, "Let me know if you need more.", "Talk later."), ""))
    return title, s, ["Will check again tomorrow."]
