"""Turn a window title and process name into a page state the skills can react to.

Pure string work, no API calls, so every branch is unit-testable off Windows. Titles are
normalised first: Edge puts a zero-width space inside "Microsoft Edge" and uses non-breaking
spaces around separators, which breaks naive substring matching.

The states the skills act on:
  ready          the app is in front and showing an ordinary page
  privacy_error  the TLS interstitial ("Your connection isn't private"). Expected on every
                 mock site while the organisers' intermediate CA is expired.
  unreachable    the host did not resolve or refused, common on mirrored sites whose links
                 point at real-world hosts
  new_tab        an empty tab, nothing to read yet
  absent         the app we asked for is not the foreground window
  unknown        the app is in front but the title says nothing useful
"""
from dataclasses import dataclass, field

READY, PRIVACY_ERROR, UNREACHABLE, NEW_TAB, ABSENT, UNKNOWN = \
    "ready", "privacy_error", "unreachable", "new_tab", "absent", "unknown"

DEFAULT_PAGE_PATTERNS: list[tuple[str, list[str]]] = [
    (PRIVACY_ERROR, ["privacy error", "connection isn't private", "connection is not private",
                     "not private", "certificate error", "err_cert", "ssl_error", "your connection",
                     # Edge titles the expired-certificate page "Clock error" ("Your clock is ahead")
                     "clock error", "clock is ahead", "clock is behind"]),
    (UNREACHABLE, ["can't be reached", "cant be reached", "can't reach this page", "no internet",
                   "page isn't working", "page isnt working", "site can't be reached", "err_name_not_resolved",
                   "err_connection", "404", "not found", "hmmm"]),
    (NEW_TAB, ["new tab", "start page", "about:blank"]),
]
DEFAULT_APPS: dict[str, dict] = {
    "browser": {"process": "msedge.exe", "markers": ["microsoft edge", "edge", "chrome", "chromium", "firefox"]},
    "word": {"process": "winword.exe", "markers": ["word"]},
}


def normalise(title: str) -> str:
    """Lower case, strip zero-width and non-breaking characters, collapse whitespace."""
    cleaned = "".join(" " if ord(ch) in (0xA0, 0x200B, 0x200E, 0x200F, 0xFEFF) else ch for ch in title or "")
    return " ".join(cleaned.lower().split())


@dataclass(frozen=True)
class Perception:
    """Classifies the foreground window for one configured set of applications."""
    apps: dict[str, dict] = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_APPS.items()})
    page_patterns: list[tuple[str, list[str]]] = field(default_factory=lambda: list(DEFAULT_PAGE_PATTERNS))

    @classmethod
    def from_config(cls, settings: dict) -> "Perception":
        """Build from the ``perception`` config section, falling back to the defaults."""
        apps = {k: {**DEFAULT_APPS.get(k, {}), **(v or {})} for k, v in {**DEFAULT_APPS, **(settings.get("apps") or {})}.items()}
        patterns = [(state, [str(p).lower() for p in pats]) for state, pats in
                    (settings.get("page_patterns") or {}).items()] or list(DEFAULT_PAGE_PATTERNS)
        return cls(apps, patterns)

    def is_app(self, app: str, title: str, process: str = "") -> bool:
        """True when the foreground window belongs to the named app.

        The process image name is the reliable signal and wins when we have one; the title
        markers are the fallback for when process lookup is unavailable.
        """
        spec = self.apps.get(app, {})
        expected = str(spec.get("process", "")).lower()
        if process:
            return process == expected if expected else True
        clean = normalise(title)
        return any(marker in clean for marker in spec.get("markers", [])) if clean else False

    def page_state(self, title: str, process: str = "", app: str = "browser") -> str:
        """Classify the page showing in the foreground window of ``app``."""
        if not self.is_app(app, title, process):
            return ABSENT
        clean = normalise(title)
        if not clean:
            return UNKNOWN
        for state, patterns in self.page_patterns:
            if any(pattern in clean for pattern in patterns):
                return state
        return READY

    def page_name(self, title: str) -> str:
        """The leading part of a browser title, i.e. the page the user is looking at."""
        clean = normalise(title)
        for separator in (" - ", " – ", " | "):
            if separator in clean:
                return clean.split(separator)[0].strip()
        return clean
