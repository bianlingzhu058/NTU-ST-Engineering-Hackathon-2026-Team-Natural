#!/usr/bin/env bash
# Finals bundle for a VM that already has Python 3.12 installed (VM 2): app code only, as one
# base64 text file that fits through the noVNC clipboard.
#   bash packaging/build_finals.sh
# Produces dist/finals.zip and dist/finals-b64.txt, and prints the SHA256 to check on the VM.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/finals"
rm -rf "$OUT" "$ROOT/dist/finals.zip" "$ROOT/dist/finals-b64.txt"; mkdir -p "$OUT/logs"
cp -r "$ROOT/agent" "$ROOT/config" "$ROOT/ui" "$ROOT/tools" "$OUT/"
find "$OUT" -name __pycache__ -type d -exec rm -rf {} +
rm -f "$OUT/config/config.local.yaml"
( cd "$OUT" && zip -qr ../finals.zip . )
base64 -w 0 "$ROOT/dist/finals.zip" > "$ROOT/dist/finals-b64.txt"
echo "zip: $(du -h "$ROOT/dist/finals.zip" | cut -f1)  base64: $(du -h "$ROOT/dist/finals-b64.txt" | cut -f1)"
echo "SHA256: $(sha256sum "$ROOT/dist/finals.zip" | cut -c1-64 | tr a-f A-F)"
