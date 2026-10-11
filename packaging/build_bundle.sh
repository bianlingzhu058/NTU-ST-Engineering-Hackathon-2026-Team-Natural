#!/usr/bin/env bash
# Build the VM bundle: a folder that runs on Windows with nothing installed and nothing in the
# command line. Takes either
#   packaging/build_bundle.sh /path/to/python-3.11.x-embed-amd64.zip   (fresh runtime)
#   packaging/build_bundle.sh /path/to/DeskAssist.zip                  (reuse a bundle's runtime)
# Produces dist/DeskAssist.zip containing:
#   DeskAssist/runtime/DeskAssist.exe   the Python embeddable launcher, renamed
#   DeskAssist/runtime/*._pth           search path, ending in "import site" so sitecustomize runs
#   DeskAssist/app/                     agent/, config/, vendor/, tools/, sitecustomize.py, logs/
#   DeskAssist/README_VM.txt            how to make the desktop shortcut
set -euo pipefail
SOURCE="${1:?path to a python embeddable zip or a previously built DeskAssist.zip}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/DeskAssist"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
rm -rf "$ROOT/dist"; mkdir -p "$OUT/runtime" "$OUT/app"

unzip -q "$SOURCE" -d "$WORK"
if [ -d "$WORK/DeskAssist/runtime" ]; then           # reuse the runtime from an existing bundle
  cp -r "$WORK/DeskAssist/runtime/." "$OUT/runtime/"
  rm -f "$OUT"/runtime/*._pth "$OUT/runtime/DeskAssist.exe"
else                                                 # a fresh python.org embeddable zip
  cp -r "$WORK/." "$OUT/runtime/"
fi
[ -f "$OUT/runtime/pythonw.exe" ] || { echo "no pythonw.exe found in $SOURCE" >&2; exit 1; }
cp "$OUT/runtime/pythonw.exe" "$OUT/runtime/DeskAssist.exe"

# Search path for the renamed exe. CPython reads <exe name>._pth first, then python3XX._pth, so
# write both. The final "import site" is what lets app/sitecustomize.py start the run with no
# arguments on the command line.
STDLIB_ZIP="$(cd "$OUT/runtime" && ls python3*.zip | head -1)"
PTH="$(printf '%s\n.\n..\\app\n..\\app\\vendor\nimport site\n' "$STDLIB_ZIP")"
printf '%s\n' "$PTH" > "$OUT/runtime/DeskAssist._pth"
printf '%s\n' "$PTH" > "$OUT/runtime/${STDLIB_ZIP%.zip}._pth"

cp -r "$ROOT/agent" "$ROOT/config" "$ROOT/vendor" "$ROOT/tools" "$OUT/app/"
cp "$ROOT/sitecustomize.py" "$OUT/app/"
mkdir -p "$OUT/app/logs"
find "$OUT/app" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
find "$OUT/app/logs" -type f -delete 2>/dev/null || true

cat > "$OUT/README_VM.txt" <<'TXT'
DeskAssist bundle (nothing to install, no internet needed)

1. Copy the whole DeskAssist folder to C:\DeskAssist (any folder works; keep runtime and app
   together). Everything is inside it: a portable Python runtime and the agent.

2. Make the desktop shortcut. Right-click the Desktop > New > Shortcut, and for the location
   type exactly this, with NO arguments after it:

       C:\DeskAssist\runtime\DeskAssist.exe

   Name it DeskAssist. No arguments is the point: the judges read the CommandLine field in
   Sysmon, and this way it contains only the executable path.

3. Double-click the shortcut. The run length and the objective come from
   app\config\default.yaml (15 minutes of web_surfing by default). It exits on its own.

   Check it started: app\logs\agent.log gets an "autorun from sitecustomize" line, and
   app\logs\actions.jsonl gets one line per action.

   If nothing happens, the fallback shortcut target is
       C:\DeskAssist\runtime\DeskAssist.exe -m agent run
   with "Start in" set to C:\DeskAssist\app. Same behaviour, but "-m agent run" then shows up
   in the command line, so say so in the write-up if you use it.

4. To stop a run early, create an empty file named STOP_AGENT.txt inside C:\DeskAssist\app.
   The run ends between actions, never mid-keystroke.

5. Scoring your own run, inside the VM (needs a console, so use python.exe, not DeskAssist.exe):
       cd C:\DeskAssist\app
       ..\runtime\python.exe -m agent verify logs\actions.jsonl --report logs\scorecard.md
   And against the judges' own tools, after exporting from Procmon and Event Viewer:
       ..\runtime\python.exe tools\sysmon_parent_checker.py sysmon_final.xml
       ..\runtime\python.exe tools\timing_analyzer.py bot_final.csv --process DeskAssist.exe

Before a judged run: roll the VM back to the ready-for-runs snapshot, pin the browser to
taskbar slot 1 (and Word to slot 2 if you run the office objective), and keep your own mouse
off the console while it runs.
TXT
( cd "$ROOT/dist" && zip -qr DeskAssist.zip DeskAssist )
echo "built $ROOT/dist/DeskAssist.zip ($(du -h "$ROOT/dist/DeskAssist.zip" | cut -f1))"
