"""Build deliver/install_deskassist.py: one text file to paste into Notepad on a VM that already
has Python installed. It carries agent/, config/, vendor/, tools/ and sitecustomize.py as a
base64 zip plus a checksum, so a paste cut short by the VNC clipboard fails loudly instead of
installing half the code.

    python3 packaging/build_paste_installer.py [output path]

The installed copy is started from Desktop\\run_deskassist.pyw (pythonw, no console window).
That route shows python in Sysmon's CommandLine, so it is for VM2 testing; judged runs use the
DeskAssist.zip bundle.
"""
import base64
import hashlib
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "deliver" / "install_deskassist.py"

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for top in ("agent", "config", "vendor", "tools"):
        for f in sorted((ROOT / top).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                z.write(f, f.relative_to(ROOT).as_posix())
    z.write(ROOT / "sitecustomize.py", "sitecustomize.py")
raw = buf.getvalue()
b64 = base64.b64encode(raw).decode("ascii")
data = "\n".join(b64[i:i + 100] for i in range(0, len(b64), 100))

TEMPLATE = r'''# DeskAssist paste installer (version 0.3-web). Needs Python 3.11 or newer on the VM.
# 1. Paste this whole file into Notepad.
# 2. File > Save As, "Save as type: All files", name install_deskassist.py, save on the Desktop.
# 3. Double-click it. It unpacks the bot into C:\DeskAssist\app with a 3 minute run length and
#    puts run_deskassist.pyw, dryrun_deskassist.bat and verify_deskassist.bat on the Desktop.
# Nothing is downloaded. If the paste was cut short it says so and changes nothing.
import base64, hashlib, io, os, shutil, sys, zipfile, pathlib
EXPECT_SHA256 = "__SHA__"
EXPECT_BYTES = __SIZE__
DATA = """
__DATA__
"""


def fail(msg):
    print("INSTALL FAILED:", msg)
    input("Press Enter to close.")
    sys.exit(1)


if sys.version_info < (3, 11):
    fail("this Python is %d.%d; the bot needs 3.11 or newer." % sys.version_info[:2])
try:
    raw = base64.b64decode("".join(DATA.split()))
except Exception as e:
    fail("the pasted data is damaged (%s). Paste the whole file again." % e)
if len(raw) != EXPECT_BYTES or hashlib.sha256(raw).hexdigest() != EXPECT_SHA256:
    fail("the paste is incomplete (%d of %d bytes). The clipboard probably cut it off; "
         "paste the whole file again." % (len(raw), EXPECT_BYTES))

dest = pathlib.Path(os.environ.get("DESKASSIST_DEST", r"C:\DeskAssist\app"))
dest.mkdir(parents=True, exist_ok=True)
for old in ("agent", "config", "vendor", "tools"):  # drop files from an older install
    shutil.rmtree(dest / old, ignore_errors=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    z.extractall(dest)
(dest / "logs").mkdir(exist_ok=True)
stop = dest / "STOP_AGENT.txt"
if stop.exists():
    stop.unlink()

cfg = dest / "config" / "default.yaml"
cfg.write_text(cfg.read_text(encoding="utf-8").replace("minutes: 15", "minutes: 3"), encoding="utf-8")

desktop = pathlib.Path(os.environ.get("DESKASSIST_DESKTOP", pathlib.Path.home() / "Desktop"))
pyw = desktop / "run_deskassist.pyw"
pyw.write_text(
    "import logging, os, sys\n"
    "APP = r'%s'\n"
    "os.chdir(APP)\n"
    "sys.path.insert(0, APP)\n"
    "logging.basicConfig(filename=os.path.join(APP, 'logs', 'agent.log'), level=logging.INFO,\n"
    "                    format='%%(asctime)s %%(levelname)s %%(message)s')\n"
    "logging.info('run started from run_deskassist.pyw: executable=%%s', sys.executable)\n"
    "try:\n"
    "    from agent.app import run_desktop\n"
    "    run_desktop()\n"
    "    logging.info('run finished')\n"
    "except BaseException:\n"
    "    logging.exception('run ended with an exception')\n" % dest, encoding="ascii")
(desktop / "dryrun_deskassist.bat").write_text(
    "@echo off\r\ncd /d \"%s\"\r\n\"%s\" -m agent dry-run --objective web_surfing\r\npause\r\n" % (dest, sys.executable),
    encoding="ascii")
(desktop / "verify_deskassist.bat").write_text(
    "@echo off\r\ncd /d \"%s\"\r\n\"%s\" -m agent verify logs\\actions.jsonl --report logs\\scorecard.md\r\n"
    "pause\r\n" % (dest, sys.executable), encoding="ascii")

print("DeskAssist 0.3-web unpacked to", dest)
print("Python used:", sys.version.split()[0], "at", sys.executable)
print("Files:", sum(1 for f in dest.rglob("*") if f.is_file()))
print("Desktop now has:")
print("  run_deskassist.pyw     double-click to start a 3 minute run (no window appears)")
print("  dryrun_deskassist.bat  prints the plan, presses no keys")
print("  verify_deskassist.bat  scores the last run from logs\\actions.jsonl")
print("Stop early: create an empty STOP_AGENT.txt inside", dest)
input("Press Enter to close.")
'''

text = (TEMPLATE.replace("__SHA__", hashlib.sha256(raw).hexdigest())
        .replace("__SIZE__", str(len(raw))).replace("__DATA__", data))
OUT.write_text(text, encoding="ascii", newline="\r\n")
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, payload {len(raw) // 1024} KB zipped)")
