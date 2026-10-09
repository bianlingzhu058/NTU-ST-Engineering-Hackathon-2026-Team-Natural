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
    def wait(self, kind: str) -> None:
        """Wait through shared timing while respecting runner stop state."""
        self.pacer.wait(kind)


class BaseSkill(Skill):
    """Logs, times, and wraps failures around a skill's execute method."""
    def run(self, context: SkillContext, args: dict[str, Any]) -> Any:
        name, start = type(self).__name__, time.perf_counter()
        context.logger.log({"event": "skill_start", "skill": name, "args": args})
        try:
            result = self.execute(context, args)
            context.logger.log({"event": "skill_end", "skill": name, "duration_seconds": time.perf_counter() - start})
            return result
        except Exception as exc:
            context.logger.log({"event": "skill_error", "skill": name, "error": str(exc), "duration_seconds": time.perf_counter() - start})
            logging.getLogger(__name__).exception("Skill failed: %s", name)
            raise SkillError(f"{name} failed") from exc
    def execute(self, context: SkillContext, args: dict[str, Any]) -> Any:
        """Perform skill-specific work; subclasses implement this method."""
        raise NotImplementedError
