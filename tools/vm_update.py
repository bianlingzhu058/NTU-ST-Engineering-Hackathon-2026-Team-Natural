"""Small code update for the VM, from ONE paste (Kellyn 25 Oct: five 40 KB pastes per change was too slow).

On the laptop: python packaging/make_patch.py makes a patch (only the changed lines, compressed) and puts it
on the clipboard. Paste it into the noVNC clipboard box, then double-click "Update DeskAssist" on the
Desktop. This reads the clipboard, checks every file is the version the patch was made from, applies all of
it or nothing, and says which version the VM is on now.
"""
import base64
import ctypes
import hashlib
import json
import lzma
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
MAGIC = "DAPATCH1:"


def clipboard() -> str:
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetClipboardData.restype = ctypes.c_void_p
    k.GlobalLock.restype = ctypes.c_void_p
    if not u.OpenClipboard(None): return ""
    try:
        h = u.GetClipboardData(13)                     # CF_UNICODETEXT
        if not h: return ""
        p = k.GlobalLock(ctypes.c_void_p(h))
        try:
            return ctypes.wstring_at(p) if p else ""
        finally:
            k.GlobalUnlock(ctypes.c_void_p(h))
    finally:
        u.CloseClipboard()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply(patch: dict) -> list[str]:
    """All files checked and built in memory first; nothing is written unless every file fits."""
    out = {}
    for rel, f in patch["files"].items():
        path = APP / rel
        old = path.read_bytes() if path.exists() else None
        if (sha(old) if old is not None else None) != f["base"]:
            raise SystemExit(f"{rel} is not the version this patch was made from. Install the full bundle instead.")
        if f.get("delete"):
            out[rel] = None; continue
        lines = old.decode("utf-8").splitlines(keepends=True) if old is not None else []
        for i1, i2, new in reversed(f["ops"]):
            lines[i1:i2] = new
        data = "".join(lines).encode("utf-8")
        if sha(data) != f["target"]:
            raise SystemExit(f"{rel} came out wrong after patching. Nothing was changed.")
        out[rel] = data
    for rel, data in out.items():
        path = APP / rel
        if data is None:
            path.unlink(missing_ok=True); continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (APP / "VERSION").write_text(patch["target"])
    return list(out)


def main() -> None:
    text = "".join(clipboard().split())
    if not text.startswith(MAGIC):
        raise SystemExit("The clipboard does not hold an update. Paste it into the noVNC clipboard box again.")
    patch = json.loads(lzma.decompress(base64.b64decode(text[len(MAGIC):])))
    now = (APP / "VERSION").read_text().strip() if (APP / "VERSION").exists() else "?"
    if now == patch["target"]:
        print(f"Already on {now}. Nothing to do."); return
    changed = apply(patch)
    print(f"UPDATED {now} -> {patch['target']} ({len(changed)} files: {', '.join(changed)})")
    print("Close DeskAssist if it is open and start it again. Tell Claude: updated " + patch["target"])


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0): print("NOT UPDATED: " + str(e.code))
    except Exception as e:                              # show it, do not just close the window
        print("NOT UPDATED: " + repr(e))
    if sys.stdin and sys.stdin.isatty(): input("Press Enter to close")
