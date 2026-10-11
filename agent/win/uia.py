"""Read links and buttons from the foreground window through Windows UI Automation (stdlib ctypes).

Why: to click a link that is relevant, a person looks at the page. The agent cannot take
screenshots (that would cost the resource criterion and is image matching), but Chrome exposes
its page to UI Automation, the accessibility interface screen readers use. One query per page
returns each link's text and screen rectangle; the agent then picks one the way readers do
(visible without scrolling, upper-left, matching an interest) and moves the mouse to it.

It is read-only: no input is sent through UIA, no process is opened or created. The interface is
called through raw COM vtables because the VM has no comtypes/pywin32. Vtable slots follow the
declaration order in UIAutomationClient.h. Every call is wrapped; any failure makes the caller
fall back to keyboard navigation, and ``python -m agent probe`` prints what UIA sees on the VM.
"""
import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

TREE_SCOPE_DESCENDANTS = 4
PROP_CONTROL_TYPE = 30003
CONTROL = {"button": 50000, "edit": 50004, "hyperlink": 50005, "text": 50020, "document": 50030}
VT_I4 = 3
# vtable slots
UIA_ELEMENT_FROM_HANDLE, UIA_CREATE_PROPERTY_CONDITION = 6, 23
EL_FIND_ALL, EL_NAME, EL_IS_OFFSCREEN, EL_RECT = 6, 23, 38, 43
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


def _method(ptr, slot: int, *argtypes):
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[slot])


def _release(ptr) -> None:
    if ptr: _method(ptr, RELEASE)(ptr)


class Uia:
    """UI Automation client for the foreground window. ``available`` is False off Windows or on failure."""
    def __init__(self, max_elements: int = 400):
        self.available, self.error, self.queries = False, "", 0
        self._max, self._auto = max_elements, ctypes.c_void_p()
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

    def elements(self, hwnd: int, kind: str = "hyperlink", visible_only: bool = True) -> list[Element]:
        """Named elements of one control type inside the window, with screen rectangles."""
        if not self.available or not hwnd: return []
        self.queries += 1
        root, cond, arr = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        found: list[Element] = []
        try:
            if _method(self._auto, UIA_ELEMENT_FROM_HANDLE, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))(
                    self._auto, hwnd, ctypes.byref(root)) != 0 or not root: return []
            var = _VARIANT(); var.vt, var.value = VT_I4, CONTROL[kind]
            if _method(self._auto, UIA_CREATE_PROPERTY_CONDITION, ctypes.c_int, _VARIANT, ctypes.POINTER(ctypes.c_void_p))(
                    self._auto, PROP_CONTROL_TYPE, var, ctypes.byref(cond)) != 0 or not cond: return []
            if _method(root, EL_FIND_ALL, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
                    root, TREE_SCOPE_DESCENDANTS, cond, ctypes.byref(arr)) != 0 or not arr: return []
            length = ctypes.c_int()
            _method(arr, ARR_LENGTH, ctypes.POINTER(ctypes.c_int))(arr, ctypes.byref(length))
            for index in range(min(length.value, self._max)):
                element = ctypes.c_void_p()
                if _method(arr, ARR_GET, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(arr, index, ctypes.byref(element)) != 0:
                    continue
                try:
                    item = self._read(element, kind, visible_only)
                    if item: found.append(item)
                finally:
                    _release(element)
        except Exception as exc:  # pragma: no cover - Windows only
            self.error = repr(exc)
        finally:
            for ptr in (arr, cond, root): _release(ptr)
        return found

    def _read(self, element, kind: str, visible_only: bool) -> Element | None:
        offscreen = wintypes.BOOL()
        _method(element, EL_IS_OFFSCREEN, ctypes.POINTER(wintypes.BOOL))(element, ctypes.byref(offscreen))
        if visible_only and offscreen.value: return None
        rect = wintypes.RECT()
        if _method(element, EL_RECT, ctypes.POINTER(wintypes.RECT))(element, ctypes.byref(rect)) != 0: return None
        if rect.right - rect.left < 2 or rect.bottom - rect.top < 2: return None
        bstr = ctypes.c_void_p()
        name = ""
        if _method(element, EL_NAME, ctypes.POINTER(ctypes.c_void_p))(element, ctypes.byref(bstr)) == 0 and bstr.value:
            name = ctypes.wstring_at(bstr.value)
            self._oleaut.SysFreeString(bstr)
        name = " ".join(name.split())
        if not name: return None
        return Element(name, rect.left, rect.top, rect.right, rect.bottom, kind)

    def find(self, hwnd: int, kind: str, words: tuple[str, ...]) -> Element | None:
        """First visible element of ``kind`` whose name contains any of ``words`` (case-insensitive)."""
        for item in self.elements(hwnd, kind):
            lowered = item.name.lower()
            if any(word in lowered for word in words): return item
        return None


class NoUia:
    """Stand-in when UI Automation is disabled or unavailable."""
    available, error, queries = False, "disabled", 0
    def elements(self, hwnd, kind="hyperlink", visible_only=True): return []
    def find(self, hwnd, kind, words): return None
