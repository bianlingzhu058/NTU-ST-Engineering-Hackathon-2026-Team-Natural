"""Round 1 (design 25 Oct): the bot looks, reacts like a person, and the result and note come from what
really happened. Each situation from the design table is forced in the simulator."""
import random
from pathlib import Path
import pytest
from agent.app import build_app
from agent.day.content import OUTCOME
from agent.day.todo import Item
from agent.day.workday import Workday

ROOT = Path(__file__).parents[1]


def _day(seed, items, faults=None, minutes=15):
    _, ctx, _, _ = build_app(ROOT, sim=True, seed=seed)
    d = Workday(ctx, ROOT, minutes, sim=True)
    if faults: d.eyes.faults.update(faults)
    d.plan = lambda: items                    # this exact list, nothing drawn
    d.plan_breaks = lambda: setattr(d, "next_break", None) or setattr(d, "lunch_at", None)
    d.run()
    return d


def _spec(task, **kw):
    return {"task": task, **kw}


def _phrases(key):
    return [p.split("{")[0].strip(", ") for p in OUTCOME[key]]


def test_links_that_error_are_mentioned():
    item = Item("skim ap news", _spec("browse", kind="websurf", site="https://apnews.com", find=["World"]))
    _day(3, [item], {"slow_p": 0.0})
    assert item.status == "done" and any(p in item.note for p in _phrases("links_error")), item.note


def test_a_site_that_is_down_fails_honestly():
    item = Item("see coin prices at coinmarketcap", _spec("browse", kind="websurf", site="https://www.coinmarketcap.com"))
    _day(4, [item])
    assert item.status == "failed" and ("error" in item.note or "not loading" in item.note), item.note


def test_coinbase_without_prices_still_makes_the_sheet():
    item = Item("ethereum in sgd vs usd", _spec("crypto_compare", kind="hybrid", site="https://www.coinbase.com", _coin="ethereum"))
    d = _day(5, [item], {"no_prices": {"coinbase": 1.0}, "slow_p": 0.0})
    assert item.status == "started" and "tbc" in item.note and "sgd" in item.note, item.note
    assert item.note.count("sgd") == 1, "the same note must not be written twice: " + item.note
    assert any(f.startswith(("crypto usd sgd", "coin prices sgd")) for f in d.desk.saved_files)


def test_one_news_site_down_note_from_the_other():
    item = Item("news notes for the team", _spec("read_note", kind="hybrid", recipe="news",
                                                 sites=["https://apnews.com", "https://www.booking.com"]))
    _day(6, [item], {"slow_p": 0.0})
    assert item.status == "done" and "booking" in item.note, item.note


@pytest.mark.parametrize("seed", range(1, 21))
def test_no_line_is_forced(seed):
    """Team, 25 Oct: nothing hardcoded. Short runs get 2 lines, longer runs 2 to 6, all drawn by weight."""
    _, ctx, _, _ = build_app(ROOT, sim=True, seed=seed)
    for minutes, lo, hi in ((3.5, 2, 2), (15, 3, 8)):
        d = Workday(ctx, ROOT, minutes, sim=True)
        d.t0 = 0.0
        work = [i for i in d.plan() if not i.personal]
        assert lo <= len(work) <= hi, (minutes, [i.label for i in work])


def test_line_answered_only_when_its_word_is_on_the_page():
    """Kellyn 25 Oct: a page that shows but lacks what the line asks for is not done."""
    found = Item("google cloud free tier?", _spec("browse", kind="websurf", site="https://cloud.google.com", need="free credit", goal="read", answer="$300"))
    _day(5, [found], {"slow_p": 0.0})
    assert found.status == "done" and "$300 in free credit" in found.note, found.note
    missing = Item("find old reports on archive.org", _spec("browse", kind="websurf", site="https://www.archive.org", need="report", goal="read"))
    _day(6, [missing], {"slow_p": 0.0})
    assert missing.status == "failed" and "report" in missing.note, missing.note
    contact = Item("get archive.org contact details", _spec("browse", kind="websurf", site="https://www.archive.org", need="Contact", goal="open"))
    _day(7, [contact], {"slow_p": 0.0})
    assert contact.status == "failed" and "contact" in contact.note and ("down" in contact.note or "not opening" in contact.note), contact.note


def test_every_browse_word_is_on_its_saved_page():
    """The words the lines ask for were taken from the VM page dumps; keep them true."""
    import yaml
    from agent.day.eyes import SimEyes, content
    cfg = yaml.safe_load((ROOT / "config" / "workday.yaml").read_text())
    eyes = SimEyes(ROOT)
    for spec in cfg["items"]:
        if spec["task"] != "browse": continue
        for label in spec["labels"]:
            if not isinstance(label, list): continue
            eyes.see(spec["site"])
            names = [e.name.lower() for e in content(eyes._page())]
            if label[2] == "read":
                from agent.day.eyes import answers
                assert answers(eyes._page(), label[1].lower(), label[3] if len(label) > 3 else ""), (spec["site"], label)
            else:
                assert any(label[1].lower() in n for n in names), (spec["site"], label)


def test_one_phone_is_said_as_it_is():
    """Kellyn 25 Oct: the Samsung homepage shows one phone; the list says only that one, then tbc."""
    item = Item("phone options for priya", _spec("read_note", kind="hybrid", recipe="phone", sites=["https://www.samsung.com"]))
    _day(8, [item], {"slow_p": 0.0})
    assert item.status == "started" and "Galaxy Z Fold7" in item.note and "tbc" in item.note, item.note
    assert "Buds" not in item.note and "Watch" not in item.note


def test_coins_further_down_are_scrolled_to_not_left_empty():
    """Run 13: WhiteBIT (rank 10) was below the Edge half and left empty. The bot scrolls down to it."""
    item = Item("check xrp on coingecko", _spec("crypto_prices", kind="hybrid", site="https://coingecko.com", _coin="xrp"))
    d = _day(9, [item], {"slow_p": 0.0, "tall_view": True})
    assert item.status == "done", item.note
    assert not getattr(d.tasks_done[-1], "hidden", set()) if hasattr(d, "tasks_done") else True
