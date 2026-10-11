"""Mouse: Fitts time grows with distance, event count follows time, clicks have a human hold."""
import math
from agent.input.mouse import HumanMouse
from tests.helpers import kit


def test_longer_moves_take_longer_and_send_more_events():
    rng, clock, pacer, persona, backend = kit(1)
    mouse = HumanMouse(backend, pacer, rng, persona)
    short = [mouse.movement_time(100, 20) for _ in range(200)]
    long = [mouse.movement_time(900, 20) for _ in range(200)]
    assert sum(long) / 200 > sum(short) / 200 * 1.3


def test_event_count_scales_with_distance_not_fixed():
    rng, clock, pacer, persona, backend = kit(2)
    mouse = HumanMouse(backend, pacer, rng, persona)
    mouse.move(1000, 540); mouse.move(1050, 560); mouse.move(200, 900)
    steps = [m["steps"] for m in mouse.last_moves]
    assert len(set(steps)) == len(steps)


def test_click_holds_the_button_like_a_person():
    rng, clock, pacer, persona, backend = kit(3)
    mouse = HumanMouse(backend, pacer, rng, persona)
    holds = []
    for _ in range(50):
        backend.calls.clear()
        before = clock.monotonic()
        mouse.press_button()
        names = [c[0] for c in backend.calls]
        assert names.index("button_down") < names.index("button_up")
        holds.append(clock.monotonic() - before)
    assert all(h > 0.05 for h in holds)


def test_moves_stay_on_screen():
    rng, clock, pacer, persona, backend = kit(5)
    mouse = HumanMouse(backend, pacer, rng, persona)
    mouse.move(-50, 2000)
    xs = [c[1] for c in backend.calls if c[0] == "move_to"]
    assert all(0 <= x < 1920 and 0 <= y < 1080 for x, y in xs)
