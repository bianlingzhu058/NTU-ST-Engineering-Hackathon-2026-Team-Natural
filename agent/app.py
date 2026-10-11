"""Composition root wiring configuration, primitives, perception, skills and runner.

Three modes share one code path, which is the point: what runs on the VM is what the offline
tests exercise.
  real  SendInput backend, real clock, Windows window/process introspection.
  dry   fake input backend, simulated desktop, virtual clock. One objective, instantly.
  sim   the same as dry but for the full minutes budget, producing a complete action log with
        realistic timestamps that `agent verify` scores against the rubric.
"""
from pathlib import Path
import random
from .clock import RealClock, VirtualClock
from .config import AgentConfig, load_objectives
from .input.fake_backend import FakeInputBackend
from .input.keyboard import HumanTyper
from .input.mouse import HumanMouse
from .input.scroll import HumanScroller
from .logger import JsonlActionLogger
from .perception import Perception
from .runner import Runner
from .session import SessionModel
from .timing import HumanPacer
from .win.desktop import BlindDesktop, WindowsDesktop
from .win.fake_desktop import FakeDesktop
from .skills.base import SkillContext
from . import skills  # noqa: F401  registers the built-in skills


def _real_backend(name: str):
    """Pick the desktop input backend by config: sendinput (stdlib, default on Windows) or pyautogui."""
    if name == "pyautogui":
        from .input.pyautogui_backend import PyAutoGuiBackend
        return PyAutoGuiBackend()
    from .input.sendinput_backend import SendInputBackend
    return SendInputBackend()


def _real_desktop(settings: dict):
    """Windows introspection when enabled and available, otherwise a blind stand-in.

    Perception is a config switch on purpose: if the VM behaves unexpectedly on the day, the
    operator can turn it off and the agent falls back to the open-loop behaviour instead of
    failing to start.
    """
    if not settings.get("enabled", True):
        return BlindDesktop()
    try:
        return WindowsDesktop(use_process_lookup=bool(settings.get("use_process_lookup", True)))
    except Exception:
        return BlindDesktop()


def build_app(root: Path | None = None, dry_run: bool = False, seed: int | None = None, mode: str | None = None,
              log_name: str | None = None):
    """Build injected runtime components without import-time side effects."""
    root = root or Path(__file__).resolve().parent.parent
    mode = mode or ("dry" if dry_run else "real")
    config = AgentConfig.load(root / "config" / "default.yaml")
    rng = random.Random(seed) if seed is not None else random.Random()
    simulated = mode in ("dry", "sim")
    clock = VirtualClock() if simulated else RealClock()
    perception = Perception.from_config(config.section("perception"))
    if simulated:
        sim = config.section("simulation")
        desktop = FakeDesktop(random.Random(rng.randrange(2 ** 31)), float(sim.get("privacy_error_rate", 0.5)),
                              float(sim.get("unreachable_rate", 0.12)), int(sim.get("startup_polls", 2)), clock,
                              float(sim.get("link_hit_rate", 0.7)))
        backend = FakeInputBackend(observer=desktop.observe)
    else:
        desktop = _real_desktop(config.section("perception"))
        backend = _real_backend(config.section("input").get("backend", "sendinput"))
    session = SessionModel.from_config(config.section("session"), rng, clock)
    pacer = HumanPacer(config.section("timing"), rng, sleeper=clock.sleep, modulator=session.multiplier, clock=clock)
    runner_settings = config.section("runner")
    stop_file = root / runner_settings.get("stop_file", "STOP_AGENT.txt")
    log_path = root / (log_name or config.section("logging").get("path", "logs/actions.jsonl"))
    logger = JsonlActionLogger(log_path, clock=clock)
    typing_settings, mouse_settings = config.section("typing"), config.section("mouse")
    context = SkillContext(
        backend, pacer, HumanTyper(backend, pacer, rng, float(typing_settings.get("typo_rate", .02))),
        HumanMouse(backend, pacer, rng, int(mouse_settings.get("steps", 14))),
        HumanScroller(backend, pacer, rng, int(config.section("scroll").get("burst_size", 4))), logger,
        dry_run=simulated, rng=rng, desktop=desktop, perception=perception, session=session, clock=clock,
        stop_check=stop_file.exists, max_blind_actions=int(runner_settings.get("max_blind_actions", 3)))
    objectives = load_objectives(root / "config" / "objectives")
    deps = {"backend": backend, "pacer": pacer, "rng": rng}
    runner = Runner(objectives, context, deps, pacer, rng, stop_file, clock,
                    float(runner_settings.get("min_objective_seconds", 90)))
    return config, context, runner, objectives


def run_desktop(objective: str | None = None, minutes: float | None = None) -> None:
    """Entry point for the double-clicked run: objective and minutes default to config/default.yaml."""
    config, _, runner, _ = build_app()
    settings = config.section("runner")
    runner.run(float(minutes if minutes is not None else settings.get("minutes", 15)),
               objective if objective is not None else settings.get("objective") or None)
