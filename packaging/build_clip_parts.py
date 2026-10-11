"""Split a bundle zip into clipboard-sized parts for a VM reachable only through the noVNC console.

    python3 packaging/build_clip_parts.py BUNDLE.zip OUT_DIR [chars_per_part]

Writes OUT_DIR/part01.txt.. (each starts with "#PART n/total LEN k"), OUT_DIR/receive.ps1 (paste
into the VM once; it watches the clipboard, saves each part, then rebuilds and unpacks the zip
to C:\\ after a SHA256 check) and OUT_DIR/load_parts.sh (puts each part on the laptop clipboard).
A 2 MB clipboard message dropped the noVNC connection on 11 Oct; 133 KB went through.
"""
import base64
import hashlib
import sys
from pathlib import Path

bundle, out = Path(sys.argv[1]), Path(sys.argv[2])
size = int(sys.argv[3]) if len(sys.argv) > 3 else 500_000
raw = bundle.read_bytes()
b64 = base64.b64encode(raw).decode("ascii")
chunks = [b64[i:i + size] for i in range(0, len(b64), size)]
out.mkdir(parents=True, exist_ok=True)
for old in out.glob("part*.txt"):
    old.unlink()
for n, c in enumerate(chunks, 1):
    body = "\n".join(c[i:i + 76] for i in range(0, len(c), 76))
    (out / f"part{n:02d}.txt").write_text(f"#PART {n}/{len(chunks)} LEN {len(c)}\n{body}\n", encoding="ascii")

sha = hashlib.sha256(raw).hexdigest().upper()
(out / "receive.ps1").write_text(r'''# DeskAssist receiver. Leave this window open; it saves every part you paste into the noVNC
# clipboard box, then rebuilds DeskAssist.zip, checks it and unpacks it to C:\DeskAssist.
$dir = Join-Path $env:USERPROFILE "Desktop\dk"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$expect = "__SHA__"
$got = @{}; $total = 0; $lastBad = ""
Write-Host "Waiting for parts. Paste each one into the noVNC clipboard box." -ForegroundColor Cyan
while ($total -eq 0 -or $got.Count -lt $total) {
    $t = Get-Clipboard -Raw
    if ($t -and $t -match '^#PART (\d+)/(\d+) LEN (\d+)') {
        $n = [int]$Matches[1]; $total = [int]$Matches[2]; $len = [int]$Matches[3]
        if (-not $got.ContainsKey($n)) {
            $body = ($t.Substring($Matches[0].Length)) -replace '\s', ''
            if ($body.Length -eq $len) {
                [IO.File]::WriteAllText((Join-Path $dir ("p{0:D2}.b64" -f $n)), $body)
                $got[$n] = 1
                Write-Host ("Part {0} saved  ({1} of {2} done)" -f $n, $got.Count, $total) -ForegroundColor Green
            } elseif ($t -ne $lastBad) {
                $lastBad = $t
                Write-Host ("Part {0} came through incomplete ({1} of {2} chars). Paste it again." -f $n, $body.Length, $len) -ForegroundColor Red
            }
        }
    }
    Start-Sleep -Milliseconds 700
}
Write-Host "All parts in. Rebuilding the zip..." -ForegroundColor Cyan
$all = -join (1..$total | ForEach-Object { [IO.File]::ReadAllText((Join-Path $dir ("p{0:D2}.b64" -f $_))) })
$zip = Join-Path $dir "DeskAssist.zip"
[IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String($all))
$h = (Get-FileHash -Algorithm SHA256 $zip).Hash
if ($h -ne $expect) { Write-Host "CHECKSUM MISMATCH: $h" -ForegroundColor Red; Read-Host "Press Enter"; exit 1 }
Write-Host "Checksum OK. Unpacking to C:\DeskAssist ..." -ForegroundColor Cyan
Expand-Archive -Force -Path $zip -DestinationPath "C:\"
Get-ChildItem C:\DeskAssist | Format-Table Name
Write-Host "DONE. DeskAssist is in C:\DeskAssist" -ForegroundColor Green
Read-Host "Press Enter to close"
'''.replace("__SHA__", sha), encoding="ascii", newline="\r\n")

(out / "load_parts.sh").write_text(r'''#!/usr/bin/env bash
# Puts each part on the clipboard in turn. Paste it into the noVNC clipboard box, wait for the
# VM's receiver window to say "saved", then press Enter here for the next one.
cd "$(dirname "$0")"
parts=(part*.txt); n=${#parts[@]}
for f in "${parts[@]}"; do
  wl-copy < "$f"
  read -rp "$f of $n is on the clipboard. Paste it into the noVNC box, wait for 'saved', press Enter... "
done
echo "All $n parts sent."
''', encoding="ascii")
(out / "load_parts.sh").chmod(0o755)
print(f"{len(chunks)} parts of up to {size} chars, sha256 {sha}")
