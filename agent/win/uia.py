"""Read links, text, buttons and table cells from the foreground window through Windows UI Automation.

Why: to click a link that is relevant, or note a price, a person looks at the page. The agent
cannot take screenshots (that would cost the resource criterion and is image matching), but
Edge and Chrome expose their pages (and Windows its Save As box and Explorer lists) to UI Automation, the accessibility interface screen readers use.

Cost. UI Automation is cross-process: every property read is a round trip into Chrome. Reading
name, rectangle and visibility one element at a time cost three round trips per element, about
1200 for a 400-link page. So one query asks for everything at once: a cache request names the
three properties, the condition (control types OR-ed, AND not offscreen) is evaluated on the
provider side, and FindAllBuildCache returns all matches with their properties in a single call.
If that path fails on a machine, the client falls back to the per-element reads for the rest of
the run.

It is read-only: no input is sent through UIA, no process is opened or created. The interface is
called through raw COM vtables because the VM has no comtypes/pywin32. Vtable slots follow the
declaration order in UIAutomationClient.h; a wrong slot raises OSError (ctypes turns the access
violation into an exception), which is caught. ``python -m agent probe`` prints what UIA sees.

Chrome builds its page accessibility tree lazily: the first query on a fresh page can return
only the browser's own UI (VM, 15 Oct). Callers that need page content poll (wait_for_content).
"""
import ctypes
import functools
import sys
from ctypes import wintypes
from dataclasses import dataclass

TREE_SCOPE_DESCENDANTS = 4
PROP_BOUNDING_RECT, PROP_CONTROL_TYPE, PROP_NAME, PROP_IS_OFFSCREEN = 30001, 30003, 30005, 30022
CONTROL = {"button": 50000, "checkbox": 50002, "combobox": 50003, "edit": 50004, "hyperlink": 50005, "image": 50006,
           "listitem": 50007, "list": 50008, "menuitem": 50011, "tabitem": 50019, "text": 50020, "toolbar": 50021,
           "custom": 50025, "group": 50026, "dataitem": 50029, "document": 50030, "splitbutton": 50031,
           "pane": 50033, "treeitem": 50024}
KIND = {v: k for k, v in CONTROL.items()}
VT_I4, VT_BOOL = 3, 11
# IUIAutomation slots
UIA_ELEMENT_FROM_HANDLE, UIA_CREATE_CACHE_REQUEST, UIA_CREATE_PROPERTY_CONDITION = 6, 20, 23
UIA_CREATE_AND_CONDITION, UIA_CREATE_OR_CONDITION = 25, 28
# IUIAutomationElement slots (cached getters are the current ones + 32)
EL_FIND_ALL, EL_FIND_ALL_BUILD_CACHE = 6, 8
EL_NAME, EL_IS_OFFSCREEN, EL_RECT = 23, 38, 43
EL_CACHED_CONTROL_TYPE, EL_CACHED_NAME, EL_CACHED_IS_OFFSCREEN, EL_CACHED_RECT = 53, 55, 70, 75
# IUIAutomationCacheRequest, IUIAutomationElementArray, IUnknown
CR_ADD_PROPERTY = 3
ARR_LENGTH, ARR_GET = 3, 4
RELEASE = 2


@dataclass(frozen=True)
class Element:
    name: str
    left: int
    top: int
    right: int
    bottom: int
    kind: str = "hyperlink"
    url: str = ""          # only filled by the laptop simulator (from the dump files)

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2

    @property
    def width(self) -> int: return max(1, self.right - self.left)

    @property
    def height(self) -> int: return max(1, self.bottom - self.top)


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "_GUID":
        h = text.strip("{}").replace("-", "")
        return cls(int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16),
                   (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:32])))


class _VARIANT(ctypes.Structure):  # 24 bytes on x64: vt, 3 reserved words, 16-byte union
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("value", ctypes.c_longlong), ("pad", ctypes.c_void_p)]


CLSID_CUIAutomation = "{FF48DBA4-60EF-4201-AA87-54103EEF594E}"
IID_IUIAutomation = "{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}"
OUT = ctypes.POINTER(ctypes.c_void_p)


@functools.lru_cache(maxsize=None)
def _prototype(*argtypes):
    """One WINFUNCTYPE per signature, built once (building it per call was measurable overhead)."""
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)


def _call(ptr, slot: int, *args_and_types):
    """Call vtable ``slot`` of COM object ``ptr``; arguments alternate (ctype, value)."""
    types, values = args_and_types[0::2], args_and_types[1::2]
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return _prototype(*types)(vtable[slot])(ptr, *values)


def _release(ptr) -> None:
    if ptr: _call(ptr, RELEASE)


class Uia:
    """UI Automation client for the foreground window. ``available`` is False off Windows or on failure."""
    def __init__(self, max_elements: int = 400, use_cache: bool = True):
        self.available, self.error, self.queries, self.cached = False, "", 0, use_cache
        self._max, self._auto, self._request = max_elements, ctypes.c_void_p(), ctypes.c_void_p()
        self._conditions: dict = {}
        if not sys.platform.startswith("win"):
            self.error = "not windows"
            return
        try:
            ole32 = ctypes.windll.ole32
            self._oleaut = ctypes.windll.oleaut32
            ole32.CoInitializeEx(None, 0x2)
            clsid, iid = _GUID.parse(CLSID_CUIAutomation), _GUID.parse(IID_IUIAutomation)
            hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(self._auto))
            self.available = hr == 0 and bool(self._auto)
            if not self.available: self.error = f"CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}"
        except Exception as exc:  # pragma: no cover - Windows only
            self.error = repr(exc)

    # conditions and the cache request are built once and kept for the run
    def _property_condition(self, prop: int, vt: int, value: int):
        var = _VARIANT(); var.vt, var.value = vt, value
        out = ctypes.c_void_p()
        if _call(self._auto, UIA_CREATE_PROPERTY_CONDITION, ctypes.c_int, prop, _VARIANT, var, OUT, ctypes.byref(out)) != 0 \
                or not out: raise OSError("CreatePropertyCondition failed")
        return out

    def _combine(self, slot: int, a, b):
        out = ctypes.c_void_p()
        if _call(self._auto, slot, ctypes.c_void_p, a, ctypes.c_void_p, b, OUT, ctypes.byref(out)) != 0 or not out:
            raise OSError("CreateAnd/OrCondition failed")
        return out

    def _condition(self, kinds: tuple[str, ...], visible_only: bool):
        key = (kinds, visible_only)
        if key not in self._conditions:
            cond = self._property_condition(PROP_CONTROL_TYPE, VT_I4, CONTROL[kinds[0]])
            for kind in kinds[1:]:
                cond = self._combine(UIA_CREATE_OR_CONDITION, cond,
                                     self._property_condition(PROP_CONTROL_TYPE, VT_I4, CONTROL[kind]))
            if visible_only and self.cached:  # VARIANT_FALSE = 0; filtered by UIA, not in Python
                cond = self._combine(UIA_CREATE_AND_CONDITION, cond,
                                     self._property_condition(PROP_IS_OFFSCREEN, VT_BOOL, 0))
            self._conditions[key] = cond
        return self._conditions[key]

    def _cache_request(self):
        if not self._request:
            if _call(self._auto, UIA_CREATE_CACHE_REQUEST, OUT, ctypes.byref(self._request)) != 0 or not self._request:
                raise OSError("CreateCacheRequest failed")
            for prop in (PROP_NAME, PROP_BOUNDING_RECT, PROP_CONTROL_TYPE, PROP_IS_OFFSCREEN):
                if _call(self._request, CR_ADD_PROPERTY, ctypes.c_int, prop) != 0:
                    raise OSError("AddProperty failed")
        return self._request

    def elements(self, hwnd: int, kind="hyperlink", visible_only: bool = True) -> list[Element]:
        """Named elements of one or more control types inside the window, with screen rectangles.

        ``kind`` is a control type name or a tuple of them (one query for all of them).
        """
        if not self.available or not hwnd: return []
        kinds = (kind,) if isinstance(kind, str) else tuple(kind)
        self.queries += 1
        root = ctypes.c_void_p()
        try:
            if _call(self._auto, UIA_ELEMENT_FROM_HANDLE, wintypes.HWND, hwnd, OUT, ctypes.byref(root)) != 0 or not root:
                return []
            if self.cached:
                try:
                    return self._find(root, kinds, visible_only, cached=True)
                except OSError as exc:  # pragma: no cover - Windows only
                    self.error, self.cached = f"cache path off: {exc!r}", False
                    self._conditions.clear()
            return self._find(root, kinds, visible_only, cached=False)
        except Exception as exc:  # pragma: no cover - Windows only
            self.error = repr(exc)
            return []
        finally:
            _release(root)

    def _find(self, root, kinds: tuple[str, ...], visible_only: bool, cached: bool) -> list[Element]:
        cond, arr = self._condition(kinds, visible_only), ctypes.c_void_p()
        if cached:
            hr = _call(root, EL_FIND_ALL_BUILD_CACHE, ctypes.c_int, TREE_SCOPE_DESCENDANTS, ctypes.c_void_p, cond,
                       ctypes.c_void_p, self._cache_request(), OUT, ctypes.byref(arr))
            if hr != 0 or not arr: raise OSError(f"FindAllBuildCache hr=0x{hr & 0xFFFFFFFF:08X}")
        elif _call(root, EL_FIND_ALL, ctypes.c_int, TREE_SCOPE_DESCENDANTS, ctypes.c_void_p, cond,
                   OUT, ctypes.byref(arr)) != 0 or not arr:
            return []
        found: list[Element] = []
        try:
            length = ctypes.c_int()
            _call(arr, ARR_LENGTH, ctypes.POINTER(ctypes.c_int), ctypes.byref(length))
            for index in range(length.value):
                if len(found) >= self._max: break
                element = ctypes.c_void_p()
                if _call(arr, ARR_GET, ctypes.c_int, index, OUT, ctypes.byref(element)) != 0: continue
                try:
                    item = self._read(element, kinds, visible_only, cached)
                    if item: found.append(item)
                finally:
                    _release(element)
        finally:
            _release(arr)
        return found

    def _read(self, element, kinds: tuple[str, ...], visible_only: bool, cached: bool) -> Element | None:
        shift = 32 if cached else 0
        if visible_only and not cached:  # the cached query already filtered offscreen elements
            offscreen = wintypes.BOOL()
            _call(element, EL_IS_OFFSCREEN, ctypes.POINTER(wintypes.BOOL), ctypes.byref(offscreen))
            if offscreen.value: return None
        rect = wintypes.RECT()
        if _call(element, EL_RECT + shift, ctypes.POINTER(wintypes.RECT), ctypes.byref(rect)) != 0: return None
        if rect.right - rect.left < 2 or rect.bottom - rect.top < 2: return None
        bstr, name = ctypes.c_void_p(), ""
        if _call(element, EL_NAME + shift, OUT, ctypes.byref(bstr)) == 0 and bstr.value:
            name = ctypes.wstring_at(bstr.value)
            self._oleaut.SysFreeString(bstr)
        name = " ".join(name.split())
        if not name: return None
        kind = kinds[0]
        if cached and len(kinds) > 1:
            control = ctypes.c_int()
            if _call(element, EL_CACHED_CONTROL_TYPE, ctypes.POINTER(ctypes.c_int), ctypes.byref(control)) == 0:
                kind = KIND.get(control.value, kind)
        return Element(name, rect.left, rect.top, rect.right, rect.bottom, kind)

    def find(self, hwnd: int, kind: str, words: tuple[str, ...]) -> Element | None:
        """First visible element of ``kind`` whose name contains any of ``words`` (case-insensitive)."""
        for item in self.elements(hwnd, kind):
            lowered = item.name.lower()
            if any(word in lowered for word in words): return item
        return None


def find_window(needles, user32=None) -> int:
    """Handle of the first visible top-level window whose title contains one of ``needles``
    (case-insensitive, Edge's zero-width space removed). Reading a window by its handle instead of
    "whatever is in front" means a hover bubble or a pop-up cannot steal the read (VM, 24 Oct)."""
    if not sys.platform.startswith("win"): return 0
    user32 = user32 or ctypes.windll.user32
    if isinstance(needles, str): needles = [needles]
    wanted = [n.lower() for n in needles if n]
    found = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length: return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.replace("\u200b", "").lower()
        if any(w in title for w in wanted):
            found.append(hwnd)
            return False
        return True

    try:
        user32.EnumWindows(proto(visit), 0)
    except Exception:
        return 0
    return found[0] if found else 0


def front_window() -> tuple[bool, tuple[int, int, int, int]] | None:
    """(maximised?, (left, top, right, bottom)) of the window in front; None off Windows."""
    if not sys.platform.startswith("win"): return None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd: return None
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return bool(user32.IsZoomed(hwnd)), (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def alt_tab_titles(user32=None) -> list[str] | None:
    """Titles of the windows Alt+Tab shows, front to back (Windows keeps top-level windows in that
    order). Left out like Alt+Tab does: hidden, untitled, tool windows, owned dialogs, cloaked (hidden
    store app) windows. Edge TABS that Windows 11 may also list are not windows and cannot be seen
    here: switch that setting off on the VM. None off Windows."""
    if not sys.platform.startswith("win"): return None
    try:
        user32 = user32 or ctypes.windll.user32
        dwm = ctypes.windll.dwmapi
    except Exception:
        return None
    out = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length: return True
        ex = user32.GetWindowLongW(hwnd, -20)                      # GWL_EXSTYLE
        app_window = ex & 0x40000                                   # WS_EX_APPWINDOW
        if (ex & 0x80) and not app_window: return True              # WS_EX_TOOLWINDOW
        if user32.GetWindow(hwnd, 4) and not app_window: return True    # GW_OWNER: an owned dialog
        cloaked = ctypes.c_int(0)
        if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4) == 0 and cloaked.value: return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        out.append(buf.value.replace("​", ""))
        return True

    try:
        user32.EnumWindows(proto(visit), 0)
    except Exception:
        return None
    return out


def window_state(needles) -> tuple[bool, tuple[int, int, int, int]] | None:
    """(maximised?, (left, top, right, bottom)) of the window whose title holds one of ``needles``,
    read from Windows (not the bot's memory). None off Windows or when no such window is open."""
    hwnd = find_window(needles)
    if not hwnd: return None
    try:
        user32 = ctypes.windll.user32
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return bool(user32.IsZoomed(hwnd)), (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None
