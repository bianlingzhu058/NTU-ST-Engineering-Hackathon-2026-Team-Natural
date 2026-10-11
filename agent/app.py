"""Composition root wiring configuration, behaviour models, perception, skills and runner.

Three modes share one code path, which is the point: what runs on the VM is what the offline
tests exercise.
  real  SendInput backend, real clock, Windows window/process introspection, UI Automation.
  dry   fake input backend, simulated desktop, virtual clock. One objective, instantly.
  sim   the same as dry but for the full minutes budget, producing a complete action log with
        realistic timestamps that `agent verify` scores against the rubric.
"""
from pathlib import Path
import logging
import random
from .behaviour import params
from .behaviour.persona import Persona
from .clock import RealClock, VirtualClock
from .config import AgentConfig, load_objectives
from .input.fake_backend import FakeInputBackend
from .input.keyboard import HumanTyper
from .input.mouse import HumanMouse
from .input.scroll import HumanScroller
from .logger import JsonlActionLogger
from .perception import Perception
from .runner import Runner
from .timing import Pacer
from .win.desktop import BlindDesktop, WindowsDesktop
from .win.fake_desktop import FakeDesktop
from .win.uia import NoUia, Uia
from .skills.base import SkillContext
from . import skills  # noqa: F401  registers the built-in skills


def _real_backend(name: str):
    if name == "pyautogui":
        from .input.pyautogui_backend import PyAutoGuiBackend
        return PyAutoGuiBackend()
    from .input.sendinput_backend import SendInputBackend
    return SendInputBackend()


def _real_desktop(settings: dict):
    """Windows introspection when enabled and available, otherwise a blind stand-in."""
    if not settings.get("enabled", True):
        return BlindDesktop()
    try:
        return WindowsDesktop(use_process_lookup=bool(settings.get("use_process_lookup", True)))
    except Exception:
        return BlindDesktop()


def _real_uia(settings: dict):
    if not settings.get("enabled", True): return NoUia()
    uia = Uia(int(settings.get("max_elements", 400)))
    if not uia.available: logging.getLogger(__name__).info("UI Automation unavailable: %s", uia.error)
    return uia if uia.available else NoUia()


def build_app(root: Path | None = None, dry_run: bool = False, seed: int | None = None, mode: str | None = None,
              log_name: str | None = None):
    """Build injected runtime components without import-time side effects."""
    root = root or Path(__file__).resolve().parent.parent
    mode = mode or ("dry" if dry_run else "real")
    config = AgentConfig.load(root / "config" / "default.yaml")
    params.configure(config.section("behaviour"))
    rng = random.Random(seed) if seed is not None else random.Random()
    simulated = mode in ("dry", "sim")
    clock = VirtualClock() if simulated else RealClock()
    perception = Perception.from_config(config.section("perception"))
    if simulated:
        sim = config.section("simulation")
        desktop = FakeDesktop(random.Random(rng.randrange(2 ** 31)), int(sim.get("startup_polls", 3)),
                              float(sim.get("dead_link_rate", 0.25)), float(sim.get("start_center_rate", 0.2)), clock)
        backend, uia = FakeInputBackend(observer=desktop.observe), desktop
    else:
        desktop = _real_desktop(config.section("perception"))
        backend = _real_backend(config.section("input").get("backend", "sendinput"))
        uia = _real_uia(config.section("uia"))
    persona = Persona.sample(rng)
    pacer = Pacer(rng, sleeper=clock.sleep, clock=clock)
    runner_settings = config.section("runner")
    stop_file = root / runner_settings.get("stop_file", "STOP_AGENT.txt")
    log_path = root / (log_name or config.section("logging").get("path", "logs/actions.jsonl"))
    logger = JsonlActionLogger(log_path, clock=clock)
    typer = HumanTyper(backend, pacer, rng, persona)
    mouse = HumanMouse(backend, pacer, rng, persona)
    scroller = HumanScroller(backend, pacer, rng, mouse)
    context = SkillContext(backend, pacer, typer, mouse, scroller, logger, persona, dry_run=simulated, rng=rng,
                           desktop=desktop, perception=perception, uia=uia, clock=clock, stop_check=stop_file.exists,
                           max_blind_actions=int(runner_settings.get("max_blind_actions", 3)))
    objectives = load_objectives(root / "config" / "objectives")
    runner = Runner(objectives, context, {}, pacer, rng, stop_file, clock,
                    float(runner_settings.get("min_objective_seconds", 75)))
    return config, context, runner, objectives


def run_desktop(objective: str | None = None, minutes: float | None = None) -> None:
    """Entry point for the double-clicked run: objective and minutes default to config/default.yaml.

    Ctrl+Alt+F10 stops the run from any window (Lin's hotkeys module); it drops the stop file,
    so the run ends between actions, never mid-keystroke.
    """
    from .hotkeys import GlobalHotkeys
    config, context, runner, _ = build_app()
    settings = config.section("runner")
    stop_path = Path(__file__).resolve().parent.parent / settings.get("stop_file", "STOP_AGENT.txt")
    stop_path.unlink(missing_ok=True)  # a stop file left over from the last run must not end this one
    hotkeys = GlobalHotkeys(on_stop=lambda: stop_path.touch(exist_ok=True))
    hotkeys.start()
    try:
        runner.run(float(minutes if minutes is not None else settings.get("minutes", 15)),
                   objective if objective is not None else settings.get("objective") or None)
    finally:
        hotkeys.stop()
