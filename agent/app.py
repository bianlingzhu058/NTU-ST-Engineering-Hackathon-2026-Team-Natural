"""Composition root wiring configuration, primitives, skills, and runner."""
from pathlib import Path
import random
import sys
from .config import AgentConfig, load_objectives
from .input.fake_backend import FakeInputBackend
from .input.keyboard import HumanTyper
from .input.mouse import HumanMouse
from .input.scroll import HumanScroller
from .input.win_state import WindowSensor
from .logger import JsonlActionLogger
from .runner import Runner
from .hotkeys import GlobalHotkeys
from .timing import HumanPacer, SimClock
from .behaviour import params as behaviour_params
from .skills.base import SkillContext
from . import skills  # noqa: F401  registers the built-in skills


def _real_backend(name: str):
    """Pick the desktop input backend by config: sendinput (stdlib, default on Windows) or pyautogui."""
    if name == "pyautogui":
        from .input.pyautogui_backend import PyAutoGuiBackend
        return PyAutoGuiBackend()
    from .input.sendinput_backend import SendInputBackend
    return SendInputBackend()


def build_app(root: Path | None = None, dry_run: bool = False, seed: int | None = None, sim: bool = False):
    """Build injected runtime components without import-time side effects.

    sim=True (laptop simulation): fake input, and a simulated clock that every pause moves
    forward, so a whole workday runs in seconds with all its timing still sampled."""
    root = root or Path(__file__).resolve().parent.parent
    config = AgentConfig.load(root / "config" / "default.yaml")
    behaviour_params.configure(config.section("behaviour"))
    rng = random.Random(seed) if seed is not None else random.Random()
    dry_run = dry_run or sim
    backend = FakeInputBackend() if dry_run else _real_backend(config.section("input").get("backend", "sendinput"))
    if sim:
        clock = SimClock()
        pacer = HumanPacer(config.section("timing"), rng, sleeper=clock.advance, clock=clock.now)
    else:
        pacer = HumanPacer(config.section("timing"), rng, sleeper=(lambda _: None) if dry_run else __import__("time").sleep)
    logging_cfg = config.section("logging")
    logger = JsonlActionLogger(root / logging_cfg.get("path", "logs/actions.jsonl"),
                               mode="off" if sim else logging_cfg.get("mode", "buffered"))
    # Window-state sensor: live on the Windows VM, inert in dry runs (so skills fall back
    # to fixed waits). Reads foreground window titles only — never the screen.
    sensor = None if dry_run else WindowSensor()
    typer = HumanTyper(backend, pacer, rng, config.section("typing").get("typo_rate"))
    if hasattr(backend, "set_humanizer"):
        backend.set_humanizer(typer)          # every Enter, Tab and shortcut is held like a person's
    context = SkillContext(backend, pacer, typer,
                           HumanMouse(backend, pacer, rng, config.section("mouse").get("steps", 14)),
                           HumanScroller(backend, pacer, rng, config.section("scroll").get("burst_size", 4)), logger, dry_run, rng,
                           sensor=sensor)
    objectives = load_objectives(root / "config" / "objectives")
    deps = {"backend": backend, "pacer": pacer, "rng": rng}
    runner = Runner(objectives, context, deps, pacer, rng, root / config.section("runner").get("stop_file", "STOP_AGENT.txt"))
    return config, context, runner, objectives


def run_workday(context, minutes: float, root: Path | None = None, sim: bool = False) -> dict:
    """The workday mode: the bot's own to do list, worked through until the set time is up."""
    from .day.workday import Workday
    root = root or Path(__file__).resolve().parent.parent
    day = Workday(context, root, minutes, sim=sim)
    try:
        return day.run()
    finally:
        flush = getattr(context.logger, "flush", None)
        if callable(flush): flush()


def run_desktop(objective: str | None = None, minutes: float | None = None) -> None:
    """Entry point for the double-clicked run: objective and minutes default to config/default.yaml."""
    config, _, runner, _ = build_app()
    settings = config.section("runner")
    stop_path = Path(__file__).resolve().parent.parent / settings.get("stop_file", "STOP_AGENT.txt")

    def request_stop() -> None:
        stop_path.touch(exist_ok=True)

    hotkeys = GlobalHotkeys(on_stop=request_stop)
    hotkeys.start()
    chosen = objective if objective is not None else settings.get("objective")
    try:
        if chosen == "workday":
            stop_path.unlink(missing_ok=True)
            runner._pacer.set_stop(lambda: stop_path.exists())
            run_workday(runner._context, float(minutes if minutes is not None else settings.get("minutes", 15)))
            return
        runner.run(float(minutes if minutes is not None else settings.get("minutes", 15)),
                   objective if objective is not None else settings.get("objective") or None)
    finally:
        hotkeys.stop()
