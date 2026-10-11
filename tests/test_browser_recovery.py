"""The mock sites misbehave in two specific ways; both must be handled, not walked past.

The organisers' intermediate CA expired on 9 Jul 2026, so navigation lands on the certificate
interstitial, and mirrored pages link to hosts that do not resolve inside the VM.
"""
import random
from pathlib import Path
import pytest
from agent.app import build_app
from agent.skills.base import SkillError
from agent.skills.browser import GoToUrlSkill, FollowLinkSkill, ScrollAndReadSkill, DismissInterstitialSkill
from agent.skills.launch import OpenAppSkill
from agent.win.fake_desktop import FakeDesktop

ROOT = Path(__file__).parents[1]


def _browsing(seed=2, **desktop_kwargs):
    _, context, _, _ = build_app(ROOT, mode="dry", seed=seed, log_name="logs/test.jsonl")
    context.desktop = FakeDesktop(random.Random(seed), clock=context.clock, **desktop_kwargs)
    context.backend._observer = context.desktop.observe
    OpenAppSkill().run(context, {"app": "browser", "name": "edge", "taskbar_slot": 1})
    return context


def test_certificate_interstitial_is_cleared_and_recorded():
    context = _browsing(privacy_error_rate=1.0, unreachable_rate=0.0)
    args = {"url": "https://www.apple.com"}
    assert GoToUrlSkill().run(context, args) == "recovered"
    assert args["interstitial"].startswith("bypass_phrase")


def test_bypass_phrase_is_the_fallback_when_advanced_continue_does_not_work():
    context = _browsing(privacy_error_rate=1.0, unreachable_rate=0.0)
    context.desktop._rng = random.Random(0)
    args = {"url": "https://www.apple.com", "strategies": ["bypass_phrase"]}
    assert GoToUrlSkill().run(context, args) == "recovered"
    typed = "".join(payload for name, payload in context.backend.calls if name == "write")
    assert "thisisunsafe" in typed


def test_interstitial_that_never_clears_is_reported_not_ignored():
    context = _browsing(privacy_error_rate=1.0, unreachable_rate=0.0)
    context.desktop._clear_interstitial = lambda: None  # the warning never goes away
    args = {"url": "https://www.apple.com", "timeout": 3}
    assert GoToUrlSkill().run(context, args) == "privacy_error"
    assert args["interstitial"].endswith(":failed")


def test_dead_host_sends_the_agent_back_instead_of_reading_an_error_page():
    context = _browsing(privacy_error_rate=0.0, unreachable_rate=1.0)
    args = {"url": "https://www.dell.com", "back_on_dead_page": 1.0}
    assert GoToUrlSkill().run(context, args) == "unreachable"
    assert args["went_back"] is True


def test_reading_is_skipped_on_an_error_page():
    context = _browsing(privacy_error_rate=0.0, unreachable_rate=1.0)
    GoToUrlSkill().run(context, {"url": "https://www.dell.com", "back_on_dead_page": 0.0})
    args = {"bursts_range": [3, 3]}
    assert ScrollAndReadSkill().run(context, args) == 0
    assert args["outcome"] == "skipped_unreachable"


def test_following_a_link_that_hits_nothing_is_logged_as_a_misclick_not_retried():
    context = _browsing(privacy_error_rate=0.0, unreachable_rate=0.0, link_hit_rate=0.0)
    GoToUrlSkill().run(context, {"url": "https://apnews.com"})
    args = {"tabs_range": [4, 6], "timeout": 3}
    assert FollowLinkSkill().run(context, args) == "no_change"


def test_following_a_link_uses_f6_focus_before_tabbing():
    """Tabbing straight from the address bar walks Edge's own toolbar buttons instead of the page."""
    context = _browsing(privacy_error_rate=0.0, unreachable_rate=0.0)
    GoToUrlSkill().run(context, {"url": "https://apnews.com"})
    context.backend.calls.clear()
    FollowLinkSkill().run(context, {"tabs_range": [4, 4], "timeout": 3})
    names = [(name, payload) for name, payload in context.backend.calls]
    assert ("press", "f6") in names and names.index(("press", "f6")) < names.index(("press", "tab"))


def test_dismiss_interstitial_is_a_no_op_on_a_normal_page():
    context = _browsing(privacy_error_rate=0.0, unreachable_rate=0.0)
    GoToUrlSkill().run(context, {"url": "https://apnews.com"})
    assert DismissInterstitialSkill().run(context, {}) == "nothing_to_do"


def test_skills_refuse_to_act_when_the_browser_is_not_in_front():
    _, context, _, _ = build_app(ROOT, mode="dry", seed=5, log_name="logs/test.jsonl")
    with pytest.raises(SkillError):
        GoToUrlSkill().run(context, {"url": "https://www.apple.com"})


def test_bypass_phrase_is_typed_literally_with_no_simulated_typos():
    """Chromium matches the phrase as a contiguous keystroke sequence; a typo would never match."""
    context = _browsing(privacy_error_rate=1.0, unreachable_rate=0.0)
    context.typer._typo_rate = 1.0  # every key would be mistyped if the phrase went through the typer
    context.desktop._rng = random.Random(0)
    context.backend.calls.clear()
    GoToUrlSkill().run(context, {"url": "https://www.apple.com", "strategies": ["bypass_phrase"]})
    typed = "".join(payload for name, payload in context.backend.calls if name == "write")
    assert "thisisunsafe" in typed
