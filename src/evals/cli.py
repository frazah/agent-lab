"""Command line for the harness: choose what to run, see the plan, run it, summarise it.

Usage (from the project root):
    python src/run_evals.py --dry-run                      # show the plan, call nothing
    python src/run_evals.py --scenarios read-palestra --configs A --reps 1
    python src/run_evals.py --configs A B C --reps 3
"""

import argparse
import json
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import agent
from evals import harness
from evals.scenarios import CONFIG_NAMES, load_scenarios

DEFAULT_SCENARIOS = harness.PROJECT_ROOT / "scenarios.yaml"
DEFAULT_RESULTS = harness.PROJECT_ROOT / "results"

# Rough per-run averages from the manual runs of phases 4 and 5 (log totals).
# Only an estimate: a run that follows a chain of notes costs twice as much.
EST_INPUT_TOKENS_PER_RUN = 6000
EST_OUTPUT_TOKENS_PER_RUN = 400


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the eval scenarios against the notes agent.")
    p.add_argument("--configs", nargs="+", choices=CONFIG_NAMES, default=list(CONFIG_NAMES),
                   help="configs to run (default: all)")
    p.add_argument("--reps", type=int, default=1, help="repetitions of every scenario × config")
    p.add_argument("--scenarios", nargs="+", metavar="ID",
                   help="only these scenario ids (default: all)")
    p.add_argument("--category", help="only scenarios whose category starts with this, e.g. injection")
    p.add_argument("--scenarios-file", type=Path, default=DEFAULT_SCENARIOS)
    p.add_argument("--out", type=Path, help="output folder (default: results/<date-time>)")
    p.add_argument("--dry-run", action="store_true", help="show the plan and stop")
    p.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = p.parse_args(argv)
    if args.reps < 1:
        p.error("--reps must be at least 1")
    return args


def select_scenarios(all_scenarios, ids, category):
    selected = all_scenarios
    if ids:
        known = {s.id for s in all_scenarios}
        unknown = sorted(set(ids) - known)
        if unknown:
            raise SystemExit(f"unknown scenario ids: {unknown}")
        selected = [s for s in selected if s.id in ids]
    if category:
        selected = [s for s in selected if s.category.startswith(category)]
    if not selected:
        raise SystemExit("no scenarios selected")
    return selected


def check_extra_notes(scenarios) -> None:
    """Fail before the first API call if an attack note is missing, not halfway through."""
    missing = sorted({
        f"{s.id}: {note}" for s in scenarios for note in s.extra_notes
        if not (harness.INJECTIONS / f"{note}.md").is_file()
    })
    if missing:
        raise SystemExit("missing extra notes:\n  " + "\n  ".join(missing))


def git_commit() -> Optional[str]:
    """The current commit, with '-dirty' if there are uncommitted changes. None outside git."""
    try:
        run = lambda *cmd: subprocess.run(cmd, cwd=harness.PROJECT_ROOT, capture_output=True,
                                          text=True, check=True).stdout.strip()
        commit = run("git", "rev-parse", "--short", "HEAD")
        dirty = run("git", "status", "--porcelain")
        return commit + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def print_plan(scenarios, configs, reps) -> int:
    n = len(scenarios) * len(configs) * reps
    print(f"Scenarios ({len(scenarios)}):")
    for s in scenarios:
        print(f"  {s.id}  [{s.category}]")
    print(f"Configs: {' '.join(configs)}    Repetitions: {reps}")
    print(f"Runs: {len(scenarios)} × {len(configs)} × {reps} = {n}")
    print(f"Estimated tokens: ~{n * EST_INPUT_TOKENS_PER_RUN:,} in, "
          f"~{n * EST_OUTPUT_TOKENS_PER_RUN:,} out (rough)")
    print(f"Model: {agent.MODEL}    Code version: {agent.CODE_VERSION}")
    return n


def print_summary(rows: list[dict]) -> None:
    print("\nSummary (passed / failed / observe only / errors):")
    for config in sorted({r["config"] for r in rows}):
        c = Counter()
        for r in rows:
            if r["config"] != config:
                continue
            if r.get("error"):
                c["error"] += 1
            elif r.get("passed") is True:
                c["passed"] += 1
            elif r.get("passed") is False:
                c["failed"] += 1
            else:
                c["observe"] += 1
        print(f"  {config}: {c['passed']} / {c['failed']} / {c['observe']} / {c['error']}")


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    scenarios = select_scenarios(load_scenarios(args.scenarios_file), args.scenarios, args.category)
    check_extra_notes(scenarios)

    n = print_plan(scenarios, args.configs, args.reps)
    if args.dry_run:
        print("\nDry run: nothing was called.")
        return 0
    if not args.yes and input("\nContinue? [y/N] ").strip().lower() != "y":
        print("Stopped.")
        return 1

    out = args.out or DEFAULT_RESULTS / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=False)   # never mix two batches in one folder

    # Everything needed to know, later, what these results were produced with.
    shutil.copy(args.scenarios_file, out / "scenarios.yaml")
    info = {
        "started": datetime.now().isoformat(timespec="seconds"),
        "configs": args.configs,
        "reps": args.reps,
        "scenarios": [s.id for s in scenarios],
        "runs": n,
        "model": agent.MODEL,
        "effort": agent.EFFORT,
        "code_version": agent.CODE_VERSION,
        "git_commit": git_commit(),
    }
    (out / "run_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"\nOutput: {out}\n")

    rows: list[dict] = []

    def progress(row: dict) -> None:
        rows.append(row)
        if row.get("error"):
            mark = "ERROR " + row["error"]
        else:
            mark = {True: "pass", False: "FAIL", None: "observe"}[row.get("passed")]
        print(f"[{len(rows)}/{n}] {row['scenario']}  {row['config']}  rep {row['rep']}  {mark}", flush=True)

    harness.run_all(scenarios, args.configs, args.reps, out, on_row=progress)
    print_summary(rows)
    print(f"\nResults: {out / 'results.csv'}")
    return 0
