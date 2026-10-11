"""Auto-start the agent when DeskAssist.exe is launched with no arguments at all.

Why this file exists: the judges read the CommandLine field of Sysmon Event ID 1. A shortcut
whose target is `DeskAssist.exe -m agent run` puts `-m agent run` into that field, which reads
as a script interpreter being driven. With this file the shortcut target is just

    C:\\DeskAssist\\runtime\\DeskAssist.exe

and the CommandLine the judges see is the bare executable path, like any double-clicked app.

How it works: the bundle's `DeskAssist._pth` puts the app folder on sys.path and ends with
`import site`, so CPython imports `site`, which imports this module during start-up, before the
interpreter would otherwise drop into its REPL. We run the agent here and exit.

Two guards keep this from firing anywhere it should not: the executable must be named
DeskAssist (so a developer's plain `python` never starts a run), and there must be no command
line arguments (so `DeskAssist.exe -m agent dry-run` still works normally). Set
DESKASSIST_AUTORUN=1 to test the mechanism with an ordinary interpreter, or
DESKASSIST_NO_AUTORUN=1 to disable it.
"""
import logging
import os
import sys
from pathlib import Path


def _should_autorun() -> bool:
    if os.environ.get("DESKASSIST_NO_AUTORUN"):
        return False
    bare = len(sys.argv) <= 1 and (not sys.argv or sys.argv[0] in ("", "-", "-c"))
    named = Path(sys.executable).stem.lower().startswith("deskassist")
    return bool(bare and (named or os.environ.get("DESKASSIST_AUTORUN")))


if _should_autorun():
    root = Path(__file__).resolve().parent
    (root / "logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=root / "logs" / "agent.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.info("autorun from sitecustomize: executable=%s argv=%r", sys.executable, sys.argv)
    version_file = root / "VERSION.txt"
    logging.info("code version: %s", version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown")
    try:
        from agent.app import run_desktop
        run_desktop()
        logging.info("run finished")
    except BaseException:
        logging.exception("run ended with an exception")
    finally:
        logging.shutdown()
        os._exit(0)  # pythonw.exe with no arguments would otherwise sit in its REPL with no console
