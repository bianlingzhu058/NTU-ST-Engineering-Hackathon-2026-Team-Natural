"""The bot's eyes: it reads what is on screen through Windows UI Automation, never through pixels.

UI Automation is the accessibility layer screen readers use. One read returns the name (text) and
the screen rectangle of every link, text, button, table cell or list item in a window, in a single
cross-process call (agent/win/uia.py). No screenshot, no OCR, no new process, nothing on disk, so
it adds nothing a security tool would flag, and a read costs about 1 to 2 s of CPU in the browser.

What the bot does with it:
  * takes numbers and text from the page it is looking at (prices, headlines, course names),
  * finds a link by its name and clicks it where it is, or finds the "To do" folder in Save As,
  * notices a 404 or an empty page from the page itself, and clicks "Agree" on a pop-up.

When a read gives nothing (it happens on some pages), the task falls back: plain browsing, or an
honest note on the to do list. It never falls back to stored numbers.

SimEyes is the laptop simulator's stand-in: it serves the real page dumps captured on VM 2 on
24 Oct (sim_pages/), so the reading logic is tested on real page content.
"""
from dataclasses import replace
import re
from pathlib import Path
from ..win.uia import Element, Uia, find_window

PAGE_KINDS = ("text", "hyperlink", "button", "dataitem")
EDGE_CHROME = {"minimize", "restore", "close", "maximize", "back", "forward", "refresh", "new tab", "close tab",
               "favorites", "collections", "browser essentials", "split screen", "tab actions menu",
               "view site information", "settings and more (alt+f)", "copilot (ctrl+shift+.)"}
SKIP_LINK_WORDS = ("sign in", "log in", "login", "sign up", "register", "account", "cart", "basket", "checkout",
                   "download", "subscribe", "cookie", "privacy", "terms", "skip to", "accessibility", "careers",
                   "investor", "contact", "app store", "google play", "javascript", "language", "logo")
POPUP_WORDS = ("i agree", "agree", "accept all", "accept", "got it", "continue", "ok")


def _clean(name: str) -> str:
    return " ".join(name.replace("​", "").split())


class Eyes:
    """Real eyes on the VM. ``available`` is False off Windows; then every read returns []."""
    def __init__(self, max_elements: int = 1500):
        self.uia = Uia(max_elements=max_elements)
        self.available = self.uia.available
        self.reads = 0

    def see(self, url: str) -> None:            # the simulator needs to know the page; real eyes look
        pass

    def window(self, needles) -> int:
        return find_window(needles)

    def read(self, needles, kinds=PAGE_KINDS, visible: bool = False) -> list[Element]:
        hwnd = self.window(needles)
        if not hwnd: return []
        self.reads += 1
        found = self.uia.elements(hwnd, kinds, visible_only=visible)
        return [replace(e, name=_clean(e.name)) for e in found]


class SimEyes:
    """Laptop simulator: the screen is the dump of the page the bot is on (sim_pages/<site>.txt).
    Sub pages are 404 on the mock range (organiser, 11 Oct), and so they are here."""
    available = True

    BLOCKED = ("booking.com", "arstechnica", "aliexpress", "binance", "cloudflare", "coinmarketcap", "bleacherreport")

    def __init__(self, root: Path, rng=None, faults: dict | None = None):
        self.dir = root / "sim_pages"
        self.url = ""
        self.reads = 0
        self.dialog_items: list[str] = []         # what the Save As / Explorer list shows
        self._cache: dict[str, list[Element]] = {}
        self.rng = rng
        # What the VM showed on 25 Oct, put in on purpose: Coinbase without prices (now), slow first
        # loads, CNN's terms pop-up, blocked sites answering 403 Forbidden.
        self.faults = {"no_prices": {"coinbase": 0.6}, "slow_p": 0.2, "popup": {"cnn": 1.0, "samsung": 1.0}}
        if faults: self.faults.update(faults)
        self._fresh = True                         # first look at a newly opened page
        self._popup_done: set[str] = set()

    def see(self, url: str) -> None:
        if url != self.url: self._fresh = True
        self.url = url
        site = self._site()
        if self.rng is not None and site in self.faults["no_prices"] and not hasattr(self, "_np_" + site):
            setattr(self, "_np_" + site, self.rng.random() < self.faults["no_prices"][site])   # fixed for the run

    viewport = None                                # (left, top, right, bottom) of the browser, once split
    hoff = 0                                       # how far the CoinGecko table is scrolled sideways (px)

    def split(self) -> None:
        """Edge on the left half (VM: 1280 px wide screen): the right hand columns are off screen. Up and
        down are not limited: on the VM, Ctrl+F on the coin brings its row into view; the dump has no scroll."""
        self.viewport = (0, 130, 640, 1040) if self.faults.get("tall_view") else (0, -10 ** 6, 640, 10 ** 6)

    voff = 0                                       # how far the page is scrolled down (px), tall_view only

    def vscroll(self, notches: int) -> None:
        """Mouse wheel over the page: positive = down."""
        self.voff = self.voff + 100 * notches         # the dump was saved scrolled down: either way is fine

    def hscroll(self, notches: int) -> None:
        """Shift + wheel over the table: positive = to the right (VM test 25 Oct). Coin names stay put."""
        self.hoff = max(0, min(700, self.hoff + 100 * notches))

    def click(self, el) -> None:
        """The simulator's side of a click on a pop-up button: the pop-up goes away."""
        self._popup_done.add(self._site())

    def window(self, needles) -> int:
        return 1

    def _site(self) -> str:
        host = self.url.split("//")[-1].split("/")[0].replace("www.", "")
        return {"aws.amazon.com": "aws", "cloud.google.com": "googlecloud", "bit.ly": "bitly"}.get(host, host.split(".")[0])

    def _page(self) -> list[Element]:
        site = self._site()
        if site not in self._cache:
            path = self.dir / f"{site}.txt"
            items, kind = [], None
            if path.exists():
                for line in path.read_text(encoding="utf-8-sig").splitlines():
                    if line.startswith("--- "):
                        kind = line.split()[1].lower(); continue
                    m = re.match(r"\s*(-?\d+),\s*(-?\d+) (.*)", line)
                    if not m or kind is None: continue
                    text, url = m.group(3), ""
                    if "  <" in text: text, url = text.split("  <", 1); url = url.rstrip(">")
                    x, y = int(m.group(1)), int(m.group(2))
                    items.append(Element(_clean(text), x, y, x + max(40, 7 * len(text[:40])), y + 20, kind, url))
            self._cache[site] = items
        return self._cache[site]

    def read(self, needles, kinds=PAGE_KINDS, visible: bool = False) -> list[Element]:
        self.reads += 1
        wanted = (kinds,) if isinstance(kinds, str) else tuple(kinds)
        if "listitem" in wanted:
            return [Element(n, 300, 200 + 22 * i, 520, 220 + 22 * i, "listitem") for i, n in enumerate(self.dialog_items)]
        if not self.url: return []
        if any(b in self.url for b in self.BLOCKED):
            return [Element("403 Forbidden", 600, 300, 800, 330, "text"), Element("nginx", 600, 350, 660, 370, "text")]
        if self.url.rstrip("/").count("/") > 2:
            return [Element("404 Not Found", 600, 300, 800, 330, "text"), Element("nginx", 600, 350, 660, 370, "text")]
        fresh, self._fresh = self._fresh, False
        if fresh and self.rng is not None and self.rng.random() < self.faults["slow_p"]:
            return []                                       # still loading on the first look
        site = self._site()
        page = [e for e in self._page() if e.kind in wanted]
        if self.voff and site == "coingecko":
            page = [replace(e, top=e.top - self.voff, bottom=e.bottom - self.voff) for e in page]
        if self.hoff and site == "coingecko":            # table cells right of the coin name moved left
            page = [replace(e, left=e.left - self.hoff, right=e.right - self.hoff)
                    if e.kind == "dataitem" and e.left > 300 else e for e in page]
        if getattr(self, "_np_" + site, False):                # page works, prices not shown today
            page = [e for e in page if not re.search(r"S?\$[\d,]+\.\d", e.name)]
        if site in self.faults["popup"] and site not in self._popup_done and "button" in wanted:
            page = [Element("I Agree", 500, 400, 580, 430, "button")] + page
        return page


# What a person takes in from a page --------------------------------------------------------------

def content(elements: list[Element]) -> list[Element]:
    """Drop the browser's own buttons and the command-line flag warning bar."""
    return [e for e in elements if e.name.lower() not in EDGE_CHROME and "command-line flag" not in e.name
            and not e.name.lower().startswith(("profile 1", "microsoft edge"))]


ERROR_WORDS = ("404 not found", "403 forbidden", "not found", "application error", "can't reach this page",
               "this page isn't working", "this site can't be reached", "502 bad gateway", "503 service")


def page_state(elements: list[Element]) -> tuple[str, str]:
    """What a person sees at a glance: ("popup", button name), ("error", what it says),
    ("loading", "") for an empty page, or ("ok", "")."""
    button = popup_button(elements)
    if button is not None: return "popup", button.name
    names = " ".join(e.name.lower() for e in elements[:60])
    hit = next((w for w in ERROR_WORDS if w in names), None)
    if hit: return "error", hit
    if len(content(elements)) < 3: return "loading", ""
    return "ok", ""


def is_error_page(elements: list[Element]) -> bool:
    names = " ".join(e.name.lower() for e in elements[:40])
    page = content(elements)
    return (any(w in names for w in ("404 not found", "403 forbidden", "not found", "application error",
                                     "can't reach this page", "this page isn't working"))
            or len(page) < 3)


def links(elements: list[Element], words=(), avoid=SKIP_LINK_WORDS) -> list[Element]:
    """Links a person might follow: real words in them, nothing to do with logins, carts or cookies;
    ones matching ``words`` first."""
    out = []
    for e in content(elements):
        if e.kind != "hyperlink" or len(e.name) < 4: continue
        low = e.name.lower()
        if any(a in low for a in avoid) or (e.url and e.url.startswith(("mailto:", "javascript:"))): continue
        out.append(e)
    if words:
        wl = [w.lower() for w in words]
        out.sort(key=lambda e: not any(w in e.name.lower() for w in wl))
    return out


def answers(elements: list[Element], word: str, must: str = "") -> list[Element]:
    """Sentences or headlines with ``word`` in them that answer a line on the list, best first. ``must``:
    the answer word the sentence has to hold ("stablecoin" for "what is xsgd?"), so a sentence that only
    names the thing ("XSGD is live on Coinbase") does not count (Kellyn, 25 Oct)."""
    must = must.lower()
    out = [e for e in content(elements) if word in e.name.lower() and must in e.name.lower()
           and len(e.name.split()) >= (3 if must else 4) and len(e.name) <= 160 and "<" not in e.name
           and not e.name.isupper()]
    if must: return sorted(out, key=lambda e: len(gist(e.name, must, 999)))
    # a real sentence or headline (6+ words) before a short section heading ("Popular QR Code Features")
    return sorted(out, key=lambda e: (len(e.name.split()) < 6, len(e.name)))


def gist(text: str, must: str = "", limit: int = 45) -> str:
    """What a person jots down: the clause that holds the answer word (or the first clause), lower case
    unless it starts with a name like XSGD, cut at a word."""
    if text.strip().endswith("?"): return "in their faq"   # a question heading, the answer sits under it
    clauses = [c.strip() for c in re.split(r"[.?!;:]\s|, |\.$", text.strip()) if c.strip()]
    t = next((c for c in clauses if must and must.lower() in c.lower()), clauses[0] if clauses else "")
    first = t.split()[0] if t else ""
    if first[1:] == first[1:].lower(): t = t[:1].lower() + t[1:]   # keep XSGD, QR as they are
    t = "".join(ch for ch in t if ch.isascii() and ch not in "'\"")   # Writer AutoCorrect would change quotes
    if len(t) > limit: t = t[:limit].rsplit(" ", 1)[0]
    return t.rstrip(" -")


def popup_button(elements: list[Element]):
    for e in elements:
        if e.kind == "button" or (e.kind == "hyperlink" and len(e.name) <= 12):
            if e.name.lower().strip() in POPUP_WORDS: return e
    return None


def headlines(elements: list[Element]) -> list[Element]:
    bad = ("kill", "shot", "shoot", "dies", "death", "gored", "dead", "murder", "strike", "jailed", "missing")
    out, seen = [], set()
    for e in content(elements):
        t = e.name
        if not (35 <= len(t) <= 85) or t.count(" ") < 5 or t.isupper() or t in seen: continue
        if not re.fullmatch(r"[A-Za-z0-9 ,.$%&'’:\-?]+", t) or any(b in t.lower() for b in bad): continue
        seen.add(t); out.append(e)
    return out


def coingecko_coins(elements: list[Element]) -> list[dict]:
    """Rows of the CoinGecko price table: cells on one line, coin name, then the $ cells."""
    rows: dict[int, list[Element]] = {}
    for e in elements:
        if e.kind != "dataitem": continue
        key = next((k for k in rows if abs(k - e.top) <= 6), e.top)
        rows.setdefault(key, []).append(e)
    coins = []
    for cells in rows.values():
        cells.sort(key=lambda c: c.left)
        names = [c for c in cells if re.fullmatch(r"[A-Z0-9_]{2,12} .+ [A-Z0-9_]{2,12}", c.name)]
        money = [c for c in cells if c.name.startswith("$")]
        if not names or not money or "_" in names[0].name: continue
        name = " ".join(names[0].name.split()[1:-1])
        # The row reads left to right: Price, 1h %, 24h %, 7d %, 24h Volume, Market Cap. The column is
        # known by its place in the WHOLE row (cells off screen are still in the list), never as "the
        # last $ cell": at half width that was 24h Volume and went into the sheet as market cap (#35).
        cap = money[2] if len(money) >= 3 else None
        coins.append({"name": name, "name_el": names[0], "price": money[0].name.lstrip("$").replace(",", ""), "price_el": money[0],
                      "market_cap": cap.name.lstrip("$").replace(",", "") if cap else "", "cap_el": cap,
                      "price_text": money[0].name, "cap_text": cap.name if cap else ""})
    return coins


def coinbase_coins(elements: list[Element]) -> list[dict]:
    out = []
    for e in elements:
        m = re.match(r"(\w+) \1 S\$([\d,\.]+) ", e.name + " ")
        if m and not any(c["name"] == m.group(1) for c in out):
            out.append({"name": m.group(1), "price_sgd": m.group(2).replace(",", ""), "el": e, "text": "S$" + m.group(2)})
    return out


def courses(elements: list[Element]) -> list[str]:
    seen = []
    for e in content(elements):
        if re.search(r"(Specialization|Professional Certificate)$", e.name) and len(e.name) < 60 and e.name not in seen:
            seen.append(e.name)
    return seen


def galaxy_models(elements: list[Element]) -> list[str]:
    seen = []
    for e in content(elements):
        for m in re.finditer(r"Galaxy (?:Z |S |A |Tab |Buds|Watch)?[A-Z]?\w*\d\w*(?: (?:Ultra|Pro|FE|Plus))?", e.name):
            name = m.group(0).strip()
            if name not in seen: seen.append(name)
    return seen


def fact_lines(elements: list[Element], must=r"\d") -> list[str]:
    """Short sentences with a number in them ('123 Availability Zones within 39 Geographic Regions')."""
    seen = []
    for e in content(elements):
        t = e.name.rstrip(".")
        if 20 <= len(t) <= 90 and re.search(must, t) and e.kind == "text" and t not in seen and "©" not in t:
            seen.append(t)
    return seen


def short_points(elements: list[Element]) -> list[str]:
    seen = []
    for e in content(elements):
        t = e.name.rstrip(".")
        if e.kind == "text" and 12 <= len(t) <= 70 and t.count(" ") >= 2 and not t.isupper() and t not in seen:
            seen.append(t)
    return seen
