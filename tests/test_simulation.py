"""End-to-end: a full-length run on the virtual clock must satisfy the rubric every time.

tests/test_timing.py proves each pause distribution is non-uniform. This proves the thing the
judges actually measure: the gaps between the agent's logged macro actions, over a whole
15 minute run, across several seeds.
"""
from pathlib import Path
import pytest
from agent import report
from agent.app import build_app

ROOT = Path(__file__).parents[1]
SEEDS = [1, 2, 3, 4]


def _run(seed: int, minutes: float = 15.0) -> dict:
    log = ROOT / f"logs/test_sim_{seed}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)
    _, _, runner, _ = build_app(ROOT, mode="sim", seed=seed, log_name=f"logs/test_sim_{seed}.jsonl")
    runner.run(minutes, "web_surfing")
    return report.summarise(list(report.runs(report.load(log)).values())[-1])


@pytest.fixture(scope="module")
def summaries():
    return {seed: _run(seed) for seed in SEEDS}


def test_inter_action_gaps_clear_the_cv_target_on_every_seed(summaries):
    for seed, summary in summaries.items():
        assert summary["gap_stats"]["cv"] > 0.4, (seed, summary["gap_stats"])


def test_no_metronome_pattern(summaries):
    for seed, summary in summaries.items():
        assert summary["gap_stats"]["near_mode_share"] < 0.30, (seed, summary["gap_stats"])


def test_reading_pauses_are_present(summaries):
    for seed, summary in summaries.items():
        assert summary["gap_stats"]["share_over_2s"] > 0.05, seed


def test_runs_complete_inside_the_budget_without_errors(summaries):
    for seed, summary in summaries.items():
        assert summary["end_reason"] == "budget_reached", (seed, summary["end_reason"])
        assert summary["errors"] == 0, (seed, summary["errors"])
        assert 12 * 60 < summary["elapsed_seconds"] <= 15 * 60 + 90, (seed, summary["elapsed_seconds"])


def test_every_run_looks_different(summaries):
    """Identical runs are themselves a robot tell, so the shape must vary with the seed."""
    shapes = {(len(s["tasks"]), s["actions"], round(s["gap_stats"]["median"], 1)) for s in summaries.values()}
    assert len(shapes) == len(summaries)


def test_browser_is_always_launched_through_the_shell_and_always_verified(summaries):
    for seed, summary in summaries.items():
        assert set(summary["launch_strategies"]) <= {"taskbar", "start_search"}, seed
        assert set(summary["launch_outcomes"]) <= {"opened", "already_open"}, (seed, summary["launch_outcomes"])


def test_certificate_interstitials_are_handled_rather_than_typed_through(summaries):
    """Half the simulated navigations hit the expired-certificate page, as the real sites do."""
    assert sum(s["interstitials"] for s in summaries.values()) > 0
    for seed, summary in summaries.items():
        assert summary["navigation_outcomes"].get("privacy_error", 0) <= 1, seed


def test_resource_counters_are_stamped_on_actions_and_stay_small(summaries):
    for seed, summary in summaries.items():
        assert summary["memory_mb"] and summary["memory_mb"]["max"] < 100, seed
        assert summary["cpu_percent"] is not None and summary["cpu_percent"] < 5, seed


def test_the_scorecard_passes_every_rubric_row(summaries):
    for seed, summary in summaries.items():
        assert report.passed(summary), (seed, report.render(summary))
