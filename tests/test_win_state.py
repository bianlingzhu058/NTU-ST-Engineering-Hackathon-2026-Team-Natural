"""The window sensor reads foreground titles, stays inert off Windows, and never blocks a run."""
import random
from agent.input.win_state import WindowSensor
from agent.skills.base import SkillContext
from agent.timing import HumanPacer


def _ctx(sensor):
    pacer = HumanPacer({}, random.Random(0), sleeper=lambda _: None)
    return SkillContext(backend=None, pacer=pacer, typer=None, mouse=None, scroller=None,
                        logger=None, sensor=sensor)


def test_sensor_is_inert_off_windows():
    s = WindowSensor(platform="linux")
    assert s.available is False
    assert s.foreground_title() is None
    assert s.foreground_matches("Edge") is None     # None => caller just proceeds


def test_sensor_matches_title_case_insensitively():
    s = WindowSensor(title_provider=lambda: "New Tab - Microsoft Edge")
    assert s.available is True
    assert s.foreground_matches(["edge"]) is True
    assert s.foreground_matches("EDGE") is True
    assert s.foreground_matches(["calc", "writer"]) is False


def test_verify_window_waits_then_confirms_the_right_window():
    # The wrong window is in front twice, then the right one appears.
    seq = iter(["Start", "Start", "Untitled 1 - OpenOffice Writer"])
    ctx = _ctx(WindowSensor(title_provider=lambda: next(seq, "Writer")))
    assert ctx.verify_window("Writer", tries=5) is True


def test_verify_window_gives_up_without_failing():
    ctx = _ctx(WindowSensor(title_provider=lambda: "Some other window"))
    assert ctx.verify_window("Writer", tries=3) is False   # never matched, but no exception


def test_verify_window_is_a_no_op_without_a_sensor():
    assert _ctx(None).verify_window("Writer") is None
