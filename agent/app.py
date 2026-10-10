"""Composition root wiring configuration, primitives, skills, and runner."""
from pathlib import Path
import random
from .config import AgentConfig, load_objectives
from .input.fake_backend import FakeInputBackend
from .input.keyboard import HumanTyper
from .input.mouse import HumanMouse
from .input.scroll import HumanScroller
from .logger import JsonlActionLogger
from .runner import Runner
from .timing import HumanPacer
from .skills.base import SkillContext
from .run_control import RunControl


def build_app(root: Path | None = None, dry_run: bool = False, seed: int | None = None,
              control: RunControl | None = None, progress_callback=None):
    """Build injected runtime components without import-time side effects."""
    root = root or Path(__file__).resolve().parent.parent
    config = AgentConfig.load(root / "config" / "default.yaml")
    rng = random.Random(seed) if seed is not None else random.Random()
    stop_file = root / config.section("runner").get("stop_file", ".agent-stop")
    control = control or RunControl(stop_file.exists)
    backend = FakeInputBackend() if dry_run else __import__("agent.input.pyautogui_backend", fromlist=["PyAutoGuiBackend"]).PyAutoGuiBackend()
    pacer = HumanPacer(config.section("timing"), rng, sleeper=(lambda _: None) if dry_run else __import__("time").sleep, control=control)
    logger = JsonlActionLogger(root / config.section("logging").get("path", "logs/actions.jsonl"))
    context = SkillContext(backend, pacer,
                           HumanTyper(backend, pacer, rng, config.section("typing").get("typo_rate", .02), control),
                           HumanMouse(backend, pacer, rng, config.section("mouse").get("steps", 14), control),
                           HumanScroller(backend, pacer, rng, config.section("scroll").get("burst_size", 4), control),
                           logger, dry_run, control)
    objectives = load_objectives(root / "config" / "objectives")
    deps = {"backend": backend, "pacer": pacer, "rng": rng}
    runner = Runner(objectives, context, deps, pacer, rng, stop_file, control=control,
                    progress_callback=progress_callback)
    return config, context, runner, objectives


def run_desktop() -> None:
    """Programmatic entry point for running a configured desktop scenario."""
    import logging
    logging.basicConfig(level=logging.INFO)
    config, _, runner, _ = build_app()
    runner.run(float(config.section("runner").get("minutes", 15)))
