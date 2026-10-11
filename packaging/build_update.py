"""Build a one-paste code update for the VM (the runtime is already there; only the app changes).

    python3 packaging/build_update.py OUT_DIR [--minutes 5] [--objective web_surfing]

Writes
  OUT_DIR/update.txt   one clipboard paste: a "#DESKASSIST-UPDATE" header line, then base64 of a zip
                       holding agent/, config/, vendor/, tools/, sitecustomize.py and VERSION.txt
  OUT_DIR/update.ps1   the receiver. Put it on the VM once (C:\\DeskAssist\\update.ps1). Each run waits
                       for an update on the clipboard, checks its SHA256, deletes the old code folders
                       (so files removed from the code do not linger), unpacks, keeps app\\logs.

--minutes / --objective bake a config/config.local.yaml into the update, so a short test run needs
no YAML typed on the VM. A build without them runs the full 15-minute mixed session.

The noVNC clipboard dropped the connection at 2 MB and passed 500 KB; this is about 130 KB.
"""
import base64
import hashlib
import io
import subprocess  # build tool on the laptop only; never imported by the agent
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["agent", "config", "vendor", "tools"]
LIMIT = 450_000


def version() -> str:
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *INCLUDE, "sitecustomize.py"],
                               capture_output=True, text=True).stdout.strip()
    except Exception:
        commit, dirty = "unknown", ""
    from agent.runner import VERSION  # noqa: E402
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"{VERSION} {commit}{'+uncommitted' if dirty else ''} built {stamp}"


def build_zip(ver: str, local: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for folder in INCLUDE:
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    archive.write(path, f"app/{path.relative_to(ROOT).as_posix()}")
        archive.write(ROOT / "sitecustomize.py", "app/sitecustomize.py")
        archive.writestr("app/VERSION.txt", ver + "\n")
        if local: archive.writestr("app/config/config.local.yaml", local)
    return buffer.getvalue()


RECEIVER = r'''# DeskAssist code update receiver. Run in PowerShell on the VM:
#   powershell -ExecutionPolicy Bypass -File C:\DeskAssist\update.ps1
# Then paste update.txt into the noVNC clipboard box. Logs in C:\DeskAssist\app\logs are kept.
$app = "C:\DeskAssist\app"
Write-Host "Waiting for an update on the clipboard (paste update.txt into the noVNC clipboard box)..." -ForegroundColor Cyan
while ($true) {
    $t = Get-Clipboard -Raw
    if ($t -and $t.StartsWith("#DESKASSIST-UPDATE")) { break }
    Start-Sleep -Milliseconds 700
}
$lines = $t -split "`n"
$head = $lines[0].Trim()
$expect = ($head -split " ")[2]
$b64 = (($lines | Select-Object -Skip 1) -join "") -replace '\s', ''
$bytes = [Convert]::FromBase64String($b64)
$sha = [BitConverter]::ToString((New-Object Security.Cryptography.SHA256Managed).ComputeHash($bytes)) -replace '-', ''
if ($sha -ne $expect) { Write-Host "Checksum mismatch: the paste was cut or changed. Copy it again." -ForegroundColor Red; exit 1 }
$zip = Join-Path $env:TEMP "deskassist_update.zip"
[IO.File]::WriteAllBytes($zip, $bytes)
foreach ($d in "agent", "config", "vendor", "tools") { if (Test-Path "$app\$d") { Remove-Item -Recurse -Force "$app\$d" } }
Expand-Archive -Force -Path $zip -DestinationPath "C:\DeskAssist"
Remove-Item $zip
Remove-Item -Force "$app\STOP_AGENT.txt" -ErrorAction SilentlyContinue
Write-Host ("Updated to: " + (Get-Content "$app\VERSION.txt")) -ForegroundColor Green
Set-Clipboard -Value "update applied"
'''


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(ROOT / "dist" / "update"))
    parser.add_argument("--minutes", type=float)
    parser.add_argument("--objective")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    ver = version()
    local = None
    if args.minutes or args.objective:
        lines = ["runner:"] + ([f"  minutes: {args.minutes:g}"] if args.minutes else []) + \
                ([f"  objective: {args.objective}"] if args.objective else [])
        local = "# test build override, baked in by build_update.py\n" + "\n".join(lines) + "\n"
        ver += f" (test: {args.minutes or 15:g} min, {args.objective or 'all tasks'})"
    data = build_zip(ver, local)
    sha = hashlib.sha256(data).hexdigest().upper()
    b64 = base64.b64encode(data).decode("ascii")
    body = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
    text = f"#DESKASSIST-UPDATE {len(data)} {sha}\n{body}\n"
    if len(text) > LIMIT:
        raise SystemExit(f"update is {len(text)} characters, over the {LIMIT} safe paste size")
    (out / "update.txt").write_text(text, encoding="ascii")
    (out / "update.ps1").write_text(RECEIVER, encoding="ascii")
    print(f"{out / 'update.txt'}: {len(text) / 1000:.0f} KB, version {ver}")


if __name__ == "__main__":
    main()
