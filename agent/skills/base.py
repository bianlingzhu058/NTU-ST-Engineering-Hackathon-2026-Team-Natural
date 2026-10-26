"""Template method and shared context for skill execution."""
from dataclasses import dataclass
import logging
import time
from typing import Any
from ..interfaces import InputBackend, Skill
from ..logger import JsonlActionLogger
from ..timing import HumanPacer
from ..input.keyboard import HumanTyper
from ..input.mouse import HumanMouse
from ..input.scroll import HumanScroller


class SkillError(RuntimeError):
    """Signals a skill failure with the skill name preserved."""


@dataclass
class SkillContext:
    """Carries injected primitives and audit logger into skill execution."""
    backend: InputBackend
    pacer: HumanPacer
    typer: HumanTyper
    mouse: HumanMouse
    scroller: HumanScroller
    logger: JsonlActionLogger
    dry_run: bool = False
    rng: Any = None
    sensor: Any = None   # WindowSensor; None or unavailable => verify_window is a no-op
    def wait(self, kind: str) -> None:
        """Wait through shared timing while respecting runner stop state."""
        self.pacer.wait(kind)

    def verify_window(self, needles: Any, tries: int = 6, wait_kind: str = "settle"):
        """Wait until the foreground window title matches one of ``needles``, retrying
        with human pauses between checks.

        Returns True if the window was confirmed in front, False if it never matched
        within ``tries``, and None if sensing is unavailable (non-Windows / dry run) —
        in which case the caller should fall back to its usual fixed wait. Never raises:
        this only makes launches more reliable, it must not make a run fail.
        """
        sensor = self.sensor
        if sensor is None or not getattr(sensor, "available", False):
            return None
        for _ in range(max(1, int(tries))):
            matched = sensor.foreground_matches(needles)
            if matched is None:
                return None
            if matched:
                return True
            self.pacer.wait(wait_kind)   # give the window a human beat to appear, then recheck
        return False


class BaseSkill(Skill):
    """Times and wraps failures around a skill's execute method.

    Exactly ONE log line is written per skill, after it finishes. The judges
    filter Process Monitor to the agent process, so these file writes are the
    timeline they measure; one write per macro action keeps that timeline
    honest, with human-scale gaps and nothing on a timer.
    """
    def __init__(self, **dependencies: Any):
        self._deps = dependencies  # injected by the registry; skills use the context, kept for subclasses

    def run(self, context: SkillContext, args: dict[str, Any]) -> Any:
        name, start = type(self).__name__, time.perf_counter()
        try:
            result = self.execute(context, args)
            context.logger.log({"event": "action", "skill": name, "args": args,
                                "duration_seconds": round(time.perf_counter() - start, 3)})
            return result
        except Exception as exc:
            context.logger.log({"event": "action_error", "skill": name, "error": str(exc),
                                "duration_seconds": round(time.perf_counter() - start, 3)})
            logging.getLogger(__name__).exception("Skill failed: %s", name)
            raise SkillError(f"{name} failed") from exc
    def execute(self, context: SkillContext, args: dict[str, Any]) -> Any:
        """Perform skill-specific work; subclasses implement this method."""
        raise NotImplementedError
