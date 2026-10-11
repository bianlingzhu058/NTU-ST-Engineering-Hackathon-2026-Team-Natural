"""Reading: short visits stay near the top, long ones may go deeper, upward bursts happen."""
from agent.input.scroll import HumanScroller
from tests.helpers import kit


def test_short_dwell_means_little_scrolling():
    rng, clock, pacer, persona, backend = kit(1)
    scroller = HumanScroller(backend, pacer, rng)
    for _ in range(50):
        result = scroller.read_page("product", 3.0)
        assert result["screens"] <= 1


def test_reading_spends_about_the_dwell():
    rng, clock, pacer, persona, backend = kit(2)
    scroller = HumanScroller(backend, pacer, rng)
    start = clock.monotonic()
    scroller.read_page("article", 40.0)
    assert 35 <= clock.monotonic() - start <= 90
