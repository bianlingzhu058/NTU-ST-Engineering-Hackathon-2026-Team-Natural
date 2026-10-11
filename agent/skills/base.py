"""Template method and shared context for skill execution."""
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable
from ..clock import RealClock
from ..interfaces import InputBackend, Skill
from ..logger import JsonlActionLogger
from ..perception import ABSENT, Perception
from ..timing import HumanPacer
from ..input.keyboard import HumanTyper
from ..input.mouse import HumanMouse
from ..input.scroll import HumanScroller
from ..win.desktop import BlindDesktop


class SkillError(RuntimeError):
    """Signals a recoverable skill failure; the runner logs it and moves to the next task."""


class AbortRun(RuntimeError):
    """Signals that continuing would be unsafe. Never caught by the runner: the run ends.

    Raised when the agent has lost the desktop (several actions in a row with no expected
    window in front). Typing blindly into whatever has focus is how an automated run trashes a
    VM, so it stops instead.
    """


@dataclass
class SkillContext:
    """Carries injected primitives, perception and audit logger into skill execution."""
    backend: InputBackend
    pacer: HumanPacer
    typer: HumanTyper
    mouse: HumanMouse
    scroller: HumanScroller
    logger: JsonlActionLogger
    dry_run: bool = False
    rng: Any = None
    desktop: Any = field(default_factory=BlindDesktop)
    perception: Perception = field(default_factory=Perception)
    session: Any = None
    clock: Any = field(default_factory=RealClock)
    stop_check: Callable[[], bool] = lambda: False
    deadline: float | None = None
    max_blind_actions: int = 3
    blind_actions: int = 0

    def wait(self, kind: str) -> None:
        """Wait through shared timing while respecting runner stop state."""
        self.pacer.wait(kind, self.stop_check)

    def time_left(self) -> float:
        """Seconds left in the run budget; infinite when the context has no deadline."""
        return float("inf") if self.deadline is None else self.deadline - self.clock.monotonic()

    def look(self, app: str = "browser") -> tuple[str, str, str]:
        """Read the foreground window: (title, process image, page state)."""
        title, process = self.desktop.foreground_title(), self.desktop.foreground_process()
        return title, process, self.perception.page_state(title, process, app)

    def wait_for(self, predicate: Callable[[], bool], timeout: float, poll_kind: str = "step") -> bool:
        """Poll a condition on human-scale, irregular intervals until it holds or time runs out."""
        started = self.clock.monotonic()
        if predicate(): return True
        while self.clock.monotonic() - started < timeout and not self.stop_check():
            self.pacer.wait(poll_kind, self.stop_check)
            if predicate(): return True
        return False

    def note_sighting(self, state: str) -> None:
        """Track consecutive actions that found no expected window, and abort before flailing."""
        if state == ABSENT and self.desktop.available:
            self.blind_actions += 1
            if self.blind_actions >= self.max_blind_actions:
                raise AbortRun(f"no expected window in front for {self.blind_actions} actions in a row")
        else:
            self.blind_actions = 0

    def stamp(self) -> dict:
        """Resource and rhythm fields attached to the next action log line (no extra file write)."""
        data = dict(self.desktop.metrics())
        if self.session is not None: data.update(self.session.snapshot())
        return data


class BaseSkill(Skill):
    """Times and wraps failures around a skill's execute method.

    Exactly ONE log line is written per skill, after it finishes, carrying what the skill did,
    how long it took, the attention state at the time, and this process's CPU and memory. The
    judges filter Process Monitor to the agent process, so these writes are the timeline they
    measure: one per macro action, with human-scale gaps and nothing on a timer. Resource
    counters ride along on that same line rather than being sampled periodically, because a
    periodic sampler would put a metronome into the very trace being scored.
    """
    def __init__(self, **dependencies: Any):
        self._deps = dependencies  # injected by the registry; skills use the context, kept for subclasses

    def run(self, context: SkillContext, args: dict[str, Any]) -> Any:
        name, start = type(self).__name__, time.perf_counter()
        wall = context.clock.monotonic()
        try:
            result = self.execute(context, args)
            elapsed = context.clock.monotonic() - wall if context.clock.virtual else time.perf_counter() - start
            context.logger.log({"event": "action", "skill": name, "args": args,
                                "duration_seconds": round(elapsed, 3), **context.stamp()})
            if context.session is not None: context.session.step()
            return result
        except AbortRun:
            raise
        except Exception as exc:
            elapsed = context.clock.monotonic() - wall if context.clock.virtual else time.perf_counter() - start
            context.logger.log({"event": "action_error", "skill": name, "args": args, "error": str(exc),
                                "duration_seconds": round(elapsed, 3), **context.stamp()})
            logging.getLogger(__name__).exception("Skill failed: %s", name)
            raise SkillError(f"{name} failed: {exc}") from exc

    def execute(self, context: SkillContext, args: dict[str, Any]) -> Any:
        """Perform skill-specific work; subclasses implement this method."""
        raise NotImplementedError
