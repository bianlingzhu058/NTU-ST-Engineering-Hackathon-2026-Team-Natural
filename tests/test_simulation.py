"""End to end: full 15 minute sessions on the virtual clock meet every rubric row."""
from pathlib import Path
import pytest
from agent import report
from agent.app import build_app

ROOT = Path(__file__).parents[1]
SEEDS = [1, 2, 3, 4]


def _run(seed: int) -> dict:
    log = ROOT / f"logs/test_sim_{seed}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)
    _, _, runner, _ = build_app(ROOT, mode="sim", seed=seed, log_name=f"logs/test_sim_{seed}.jsonl")
    runner.run(15.0)
    return report.summarise(list(report.runs(report.load(log)).values())[-1])


@pytest.fixture(scope="module")
def summaries():
    return {seed: _run(seed) for seed in SEEDS}


def test_every_rubric_row_passes(summaries):
    for seed, summary in summaries.items():
        assert report.passed(summary), (seed, report.verdicts(summary))


def test_sessions_finish_in_budget_without_errors(summaries):
    for seed, summary in summaries.items():
        assert summary["errors"] == 0 and summary["end_reason"] == "budget_reached", seed
        assert 12 * 60 < summary["elapsed_seconds"] <= 16 * 60, (seed, summary["elapsed_seconds"])


def test_all_three_task_kinds_appear_across_seeds(summaries):
    kinds = {t["task"] for s in summaries.values() for t in s["tasks"] if t["status"] == "completed"}
    assert kinds == {"web_surfing", "office_writer", "office_calc"}


def test_launches_go_through_the_shell(summaries):
    for summary in summaries.values():
        assert all(k.split("+")[0] in ("taskbar", "start_search") for k in summary["launch_strategies"])
