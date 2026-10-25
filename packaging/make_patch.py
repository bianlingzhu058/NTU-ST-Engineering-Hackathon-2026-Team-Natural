"""Make a one paste update for the VM: only the lines that changed since the version installed there.
    bash packaging/build_finals.sh          (fresh dist/finals)
    python packaging/make_patch.py          (patch against dist/installed, copied to the clipboard)
    python packaging/make_patch.py --installed   (after Kellyn says "updated <id>": dist/installed = dist/finals)
The VM side is tools/vm_update.py ("Update DeskAssist" on the Desktop)."""
import base64
import difflib
import hashlib
import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW, BASE = ROOT / "dist" / "finals", ROOT / "dist" / "installed"
MAGIC = "DAPATCH1:"


def files(tree: Path) -> dict[str, bytes]:
    return {p.relative_to(tree).as_posix(): p.read_bytes() for p in sorted(tree.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.parent.name != "logs" and p.name != "VERSION"}


def version(tree: Path) -> str:
    h = hashlib.sha256()
    for rel, data in files(tree).items():
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    return h.hexdigest()[:8].upper()


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def main() -> None:
    if "--installed" in sys.argv:
        shutil.rmtree(BASE, ignore_errors=True)
        shutil.copytree(NEW, BASE)
        print("dist/installed is now " + version(BASE)); return
    if not BASE.exists():
        raise SystemExit("no dist/installed: install the full bundle first, then run with --installed")
    old, new = files(BASE), files(NEW)
    patch = {"base": version(BASE), "target": version(NEW), "files": {}}
    for rel in sorted(set(old) | set(new)):
        a, b = old.get(rel), new.get(rel)
        if a == b: continue
        if b is None:
            patch["files"][rel] = {"base": sha(a), "delete": True}; continue
        al = a.decode("utf-8").splitlines(keepends=True) if a is not None else []
        bl = b.decode("utf-8").splitlines(keepends=True)
        ops = [[i1, i2, bl[j1:j2]] for tag, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, al, bl, autojunk=False).get_opcodes() if tag != "equal"]
        patch["files"][rel] = {"base": sha(a), "target": sha(b), "ops": ops}
    if not patch["files"]:
        print("nothing changed since " + patch["base"]); return
    text = MAGIC + base64.b64encode(lzma.compress(json.dumps(patch).encode(), preset=9)).decode()
    (ROOT / "dist" / "patch-b64.txt").write_text(text)
    try:
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
        where = "copied to the clipboard"
    except Exception:
        where = "in dist/patch-b64.txt"
    print(f"patch {patch['base']} -> {patch['target']}: {len(patch['files'])} files, {len(text)} characters, {where}")
    for rel in patch["files"]: print("  " + rel)


if __name__ == "__main__":
    main()
