"""Composition root wiring configuration, primitives, skills, and runner."""
from pathlib import Path
import random
import sys
from .config import AgentConfig, load_objectives
from .input.fake_backend import FakeInputBackend
from .input.keyboard import HumanTyper
from .input.mouse import HumanMouse
from .input.scroll import HumanScroller
from .logger import JsonlActionLogger
from .runner import Runner
from .timing import HumanPacer
from .skills.base import SkillContext
from . import skills  # noqa: F401  registers the built-in skills


def _real_backend(name: str):
    """Pick the desktop input backend by config: sendinput (stdlib, default on Windows) or pyautogui."""
    if name == "pyautogui":
        from .input.pyautogui_backend import PyAutoGuiBackend
        return PyAutoGuiBackend()
    from .input.sendinput_backend import SendInputBackend
    return SendInputBackend()


def build_app(root: Path | None = None, dry_run: bool = False, seed: int | None = None):
    """Build injected runtime components without import-time side effects."""
    root = root or Path(__file__).resolve().parent.parent
    config = AgentConfig.load(root / "config" / "default.yaml")
    rng = random.Random(seed) if seed is not None else random.Random()
    backend = FakeInputBackend() if dry_run else _real_backend(config.section("input").get("backend", "sendinput"))
    pacer = HumanPacer(config.section("timing"), rng, sleeper=(lambda _: None) if dry_run else __import__("time").sleep)
    logger = JsonlActionLogger(root / config.section("logging").get("path", "logs/actions.jsonl"))
    context = SkillContext(backend, pacer, HumanTyper(backend, pacer, rng, config.section("typing").get("typo_rate", .02)),
                           HumanMouse(backend, pacer, rng, config.section("mouse").get("steps", 14)),
                           HumanScroller(backend, pacer, rng, config.section("scroll").get("burst_size", 4)), logger, dry_run, rng)
    objectives = load_objectives(root / "config" / "objectives")
    deps = {"backend": backend, "pacer": pacer, "rng": rng}
    runner = Runner(objectives, context, deps, pacer, rng, root / config.section("runner").get("stop_file", "STOP_AGENT.txt"))
    return config, context, runner, objectives


def run_desktop(objective: str | None = None, minutes: float | None = None) -> None:
    """Entry point for the double-clicked run: objective and minutes default to config/default.yaml."""
    config, _, runner, _ = build_app()
    settings = config.section("runner")
    runner.run(float(minutes if minutes is not None else settings.get("minutes", 15)),
               objective if objective is not None else settings.get("objective") or None)
