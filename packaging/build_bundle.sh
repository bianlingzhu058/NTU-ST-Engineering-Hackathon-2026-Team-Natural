#!/usr/bin/env bash
# Build the VM bundle: a folder that runs on Windows with nothing installed.
#   packaging/build_bundle.sh /path/to/python-3.12.10-embed-amd64.zip
# Produces dist/DeskAssist.zip containing:
#   DeskAssist/runtime/   the Python embeddable runtime, pythonw.exe copied to DeskAssist.exe
#   DeskAssist/app/       agent/, config/, vendor/ (pure-Python yaml), tools/, logs/
#   DeskAssist/README_VM.txt   how to make the desktop shortcut
set -euo pipefail
EMBED="${1:?path to python-3.12.10-embed-amd64.zip}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/DeskAssist"
rm -rf "$ROOT/dist"; mkdir -p "$OUT/runtime" "$OUT/app"
unzip -q "$EMBED" -d "$OUT/runtime"
cp "$OUT/runtime/pythonw.exe" "$OUT/runtime/DeskAssist.exe"
# search path for the renamed exe: the stdlib zip, the runtime dir, our app and vendored packages
printf 'python312.zip\n.\n..\\app\n..\\app\\vendor\n' > "$OUT/runtime/python312._pth"
cp -r "$ROOT/agent" "$ROOT/config" "$ROOT/vendor" "$ROOT/tools" "$OUT/app/"
mkdir -p "$OUT/app/logs"; find "$OUT/app" -name __pycache__ -type d -exec rm -rf {} +
cat > "$OUT/README_VM.txt" <<'TXT'
DeskAssist bundle (no installation needed)

1. Copy the whole DeskAssist folder to C:\DeskAssist (any folder works, keep runtime and app together).
2. Right-click the Desktop > New > Shortcut. Location:
       C:\DeskAssist\runtime\DeskAssist.exe -m agent run
   Name it DeskAssist. Then right-click the shortcut > Properties and set "Start in" to:
       C:\DeskAssist\app
3. Double-click the shortcut. It runs for the minutes set in app\config\default.yaml (default 15)
   with the objective set there (default web_surfing), then exits on its own.
4. To stop early, press Ctrl+Alt+F10 from any app, or create STOP_AGENT.txt inside C:\DeskAssist\app.
5. Optional start key: open the shortcut's Properties and set Shortcut key to Ctrl+Alt+F9.
6. Logs: app\logs\actions.jsonl (one line per action, the task timeline) and app\logs\agent.log.

Before a judged run: roll the VM back to the ready-for-runs snapshot, pin the browser to taskbar
slot 1 and Word to slot 2, keep your own mouse off the console while it runs.
TXT
( cd "$ROOT/dist" && zip -qr DeskAssist.zip DeskAssist )
echo "built $ROOT/dist/DeskAssist.zip ($(du -h "$ROOT/dist/DeskAssist.zip" | cut -f1))"
