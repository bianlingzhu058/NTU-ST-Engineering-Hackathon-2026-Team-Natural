#!/usr/bin/env python3
"""Check Sysmon Event ID 1 (process create) exports for parents that give automation away.

Input: Event Viewer export of Sysmon/Operational, either "Save Filtered Log File As > XML"
(preferred) or "> CSV". For every process-create event it prints image, parent image and
command line, and flags:
  - a parent that is not explorer.exe (or another name passed with --allow-parent),
  - a command line with scripting flags (-NonInteractive, -ExecutionPolicy, -File, /c, -c, -m ...).

Use --image to look only at the processes the agent touches, e.g. --image msedge.exe --image winword.exe
--image DeskAssist.exe. Exit code 1 when anything is flagged. Stdlib only.
"""
import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_FLAGS = re.compile(r"(?i)(-NonInteractive|-ExecutionPolicy|-EncodedCommand|-File\s|\s/c\s|\s-c\s|-WindowStyle\s+Hidden|\.ps1|\.vbs|\.bat|\.cmd\b)")


def _strip(tag: str) -> str: return tag.split("}", 1)[-1]


def from_xml(path: Path) -> list[dict]:
    events = []
    for ev in ET.parse(path).getroot():
        rec = {"EventID": None}
        for part in ev:
            if _strip(part.tag) == "System":
                for item in part:
                    if _strip(item.tag) == "EventID": rec["EventID"] = (item.text or "").strip()
            elif _strip(part.tag) == "EventData":
                for d in part: rec[d.attrib.get("Name", "")] = (d.text or "").strip()
        events.append(rec)
    return events


def from_csv(path: Path) -> list[dict]:
    """Event Viewer CSV keeps the fields inside the message text; pull them out with regexes."""
    events = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            cols = {k.lower().replace(" ", ""): v for k, v in row.items() if k}
            msg = cols.get("message") or cols.get("description") or ""
            rec = {"EventID": (cols.get("eventid") or cols.get("event id") or "").strip()}
            for field in ("Image", "ParentImage", "CommandLine", "ParentCommandLine", "UtcTime", "User"):
                m = re.search(rf"{field}:\s*(.*)", msg)
                rec[field] = m.group(1).strip() if m else ""
            events.append(rec)
    return events


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", type=Path); p.add_argument("--image", action="append", default=[], help="only check these image names (repeatable)")
    p.add_argument("--allow-parent", action="append", default=["explorer.exe"], help="additional acceptable parent image names")
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    if a.path.suffix.lower() == ".evtx":
        sys.exit("EVTX is binary. In Event Viewer use 'Save Filtered Log File As' and choose XML or CSV.")
    events = from_xml(a.path) if a.path.suffix.lower() == ".xml" else from_csv(a.path)
    creates = [e for e in events if str(e.get("EventID")) == "1"]
    wanted = {i.lower() for i in a.image}
    allowed = {x.lower() for x in a.allow_parent}
    rows, flagged = [], 0
    for e in creates:
        image, parent, cmd = e.get("Image", ""), e.get("ParentImage", ""), e.get("CommandLine", "")
        base, pbase = re.split(r"[\\/]", image)[-1].lower(), re.split(r"[\\/]", parent)[-1].lower()
        if wanted and base not in wanted: continue
        problems = []
        if pbase not in allowed: problems.append(f"parent is {pbase or '?'}")
        if SCRIPT_FLAGS.search(cmd): problems.append("scripting flags in command line")
        flagged += bool(problems)
        rows.append(f"| {e.get('UtcTime', '')} | {base} | {pbase} | `{cmd[:80]}` | {'FLAG: ' + '; '.join(problems) if problems else 'ok'} |")
    out = ["# Sysmon parent check", "", f"file: {a.path.name}, process-create events: {len(creates)}, checked: {len(rows)}, flagged: {flagged}", "",
           "| UtcTime | Image | ParentImage | CommandLine | Verdict |", "|---|---|---|---|---|"] + rows + ["",
           "RESULT: " + ("PASS, every checked process has an acceptable parent and a clean command line" if not flagged else f"FAIL, {flagged} flagged"), ""]
    text = "\n".join(out); print(text)
    if a.report: a.report.write_text(text, encoding="utf-8")
    sys.exit(1 if flagged else 0)


if __name__ == "__main__": main()
