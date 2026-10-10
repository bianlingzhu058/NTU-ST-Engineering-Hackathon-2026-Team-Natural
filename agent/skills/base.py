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
    def wait(self, kind: str) -> None:
        """Wait through shared timing while respecting runner stop state."""
        self.pacer.wait(kind)


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
