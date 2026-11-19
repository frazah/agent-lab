"""Run every scenario in every config, several times, and write results.csv.

For each run:
  1. copy the base notes and the scenario's extra notes into a fresh temporary folder
  2. run the agent on the scenario's request, with its own trace file
  3. judge the trace (checks.py) and measure it (metrics.py)
  4. write one row of results.csv
"""

import csv
import shutil
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from typing import Callable

import agent
from evals.checks import overall, run_checks
from evals.metrics import RunMetrics, compute_metrics
from evals.scenarios import Expected, Scenario
from store import NoteStore
from tracer import Tracer, load_events

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_NOTES = PROJECT_ROOT / "fixtures" / "base_notes"
INJECTIONS = PROJECT_ROOT / "fixtures" / "injections"

# Every row has the same columns. A check the scenario doesn't use stays empty.
CHECK_NAMES = list(Expected.model_fields)
COLUMNS = (
    ["scenario", "category", "config", "rep", "passed"]
    + [f"check_{name}" for name in CHECK_NAMES]
    + ["failures"]
    + [f.name for f in fields(RunMetrics)]
    + ["error", "log"]
)


def build_world(dest: Path, extra_notes: list[str], injections: Path = INJECTIONS) -> Path:
    """Copy the base notes and the extra notes into dest, like reset.sh does."""
    shutil.copytree(BASE_NOTES, dest)
    for note_id in extra_notes:
        src = injections / f"{note_id}.md"
        if not src.is_file():
            # A run without its attack note would measure nothing.
            raise FileNotFoundError(f"extra note not found: {src}")
        shutil.copy(src, dest / src.name)
    return dest


def run_one(scenario: Scenario, config_name: str, rep: int, logs_dir: Path,
            injections: Path = INJECTIONS) -> dict:
    """Run one scenario once in one config and return its row for the CSV."""
    config = agent.CONFIGS[config_name]
    log_path = logs_dir / f"{scenario.id}__{config_name}__{rep}.jsonl"
    row: dict = {"scenario": scenario.id, "category": scenario.category,
                 "config": config_name, "rep": rep, "log": log_path.name}

    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = build_world(Path(tmp) / "notes", scenario.extra_notes, injections)
        store = NoteStore(path=notes_dir)
        tracer = Tracer(log_path)
        # In C the user always says no, to measure what happens without consent.
        # A and B never call it.
        confirm = agent.traced_confirm(store, tracer, lambda note_id, title: False)

        try:
            agent.run_agent(store, config, scenario.request, tracer, confirm)
        except Exception as e:
            # One failed run must not stop the batch. run_agent has already
            # closed the trace with reason="error", so the run can still be judged.
            row["error"] = repr(e)

    if not log_path.exists():
        row.setdefault("error", "no trace written")
        return row

    events = load_events(log_path)
    results = run_checks(scenario.expected_for(config_name), events)
    row["passed"] = overall(results)
    for r in results:
        row[f"check_{r.name}"] = r.passed
    row["failures"] = "; ".join(f"{r.name}: {r.detail}" for r in results if not r.passed)
    row.update(asdict(compute_metrics(scenario, events)))
    return row


def run_all(scenarios: list[Scenario], configs: list[str], reps: int, out_dir: Path,
            on_row: Callable[[dict], None] | None = None,
            injections: Path = INJECTIONS) -> Path:
    """Run every scenario × config × rep and write out_dir/results.csv. Return its path."""
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        # Repetitions are the outer loop: if the API changes behaviour during a
        # long batch, every config is affected in the same way.
        for rep in range(1, reps + 1):
            for scenario in scenarios:
                for config_name in configs:
                    row = run_one(scenario, config_name, rep, logs_dir, injections)
                    writer.writerow(row)
                    f.flush()   # on disk now: a later crash doesn't lose this row
                    if on_row:
                        on_row(row)
    return csv_path
