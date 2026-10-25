"""One-off VM probe (not part of the bot): can the eyes (UI Automation) see inside OpenOffice Writer when
Windows says a screen reader is running? Prints what it finds and copies the report to the clipboard.

    python C:\\Finals\\app\\tools\\writer_probe.py

Steps it walks you through:
1. switches on the Windows "screen reader is running" flag (SPI_SETSCREENREADER),
2. you open Writer and type three short lines,
3. it reads the Writer window: text lines with their screen positions, buttons (looking for Strikethrough),
4. it switches the flag back off.
"""
import ctypes
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from agent.win.uia import Uia, find_window

SPI_GETSCREENREADER, SPI_SETSCREENREADER, SPIF_SENDCHANGE = 0x0046, 0x0047, 0x0002
user32 = ctypes.windll.user32
out = []


def say(line=""):
    print(line); out.append(line)


def flag(on: bool) -> bool:
    ok = user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1 if on else 0, None, SPIF_SENDCHANGE)
    now = ctypes.c_int(0)
    user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(now), 0)
    return bool(ok) and bool(now.value) == on


def read_writer(label: str) -> None:
    hwnd = find_window(["OpenOffice Writer"])
    say(f"--- {label}: Writer window found: {bool(hwnd)}")
    if not hwnd: return
    uia = Uia(max_elements=3000)
    kinds = ("text", "edit", "document", "button", "splitbutton", "custom", "group", "pane", "listitem", "toolbar")
    found = uia.elements(hwnd, kinds, visible_only=False)
    say(f"elements read: {len(found)}  (uia error: {uia.error or 'none'})")
    by_kind = {}
    for e in found: by_kind.setdefault(e.kind, []).append(e)
    for k, es in sorted(by_kind.items()):
        say(f"  {k}: {len(es)}")
    say("text-like elements (name, left, top, right, bottom):")
    for e in [e for e in found if e.kind in ("text", "edit", "document", "custom", "pane")][:40]:
        say(f"  [{e.kind}] {e.name[:70]!r} {e.left},{e.top},{e.right},{e.bottom}")
    strike = [e for e in found if "strike" in e.name.lower()]
    say(f"Strikethrough button visible: {bool(strike)} {[(e.kind, e.name, e.left, e.top) for e in strike][:3]}")
    say("first 30 buttons: " + ", ".join(e.name for e in found if e.kind in ("button", "splitbutton"))[:900])


say(f"screen reader flag before: {bool(ctypes.c_int(0).value)}")
read_writer("BEFORE (flag off): open Writer first if you want this baseline")
say(f"switching the screen reader flag ON: {flag(True)}")
input("\nNow CLOSE every Writer window, open Writer again (Start, writer), type three short lines\n"
      "(for example: one / two two / three), then come back here and press Enter... ")
read_writer("AFTER (flag on)")
say(f"switching the screen reader flag OFF again: {flag(False)}")
try:
    import subprocess
    subprocess.run(["clip"], input="\n".join(out).encode("utf-16le"), check=False)
    say("\nReport copied to the clipboard: paste it into the noVNC box, Ctrl+A, Ctrl+C, and send it to Claude.")
except Exception as exc:
    say(f"(could not copy to clipboard: {exc})")
input("Press Enter to close.")
