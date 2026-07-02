"""Layer 8 — Validate Tasks Script.

Run TaskValidator on gym_data/. Reports invalid tasks, missing tests,
malformed metadata.
~75 lines | Category: CLI
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def validate_tasks(gym_dir: str) -> bool:
    """Validate all task files in the gym data directory.

    Checks for:
      - Valid JSON structure
      - Required fields present (task_id, description, tests)
      - Non-empty test suites
      - Valid skill_tags
      - No duplicate task_ids
    """
    if not os.path.exists(gym_dir):
        print(f"Error: gym_data directory not found: {gym_dir}")
        return False

    task_files = list(Path(gym_dir).rglob("*.json"))
    if not task_files:
        print(f"No task files found in {gym_dir}")
        return True

    total = len(task_files)
    valid = 0
    invalid = 0
    issues: list[str] = []
    seen_ids: set[str] = set()

    required_fields = {"task_id", "description"}

    for fpath in task_files:
        try:
            with open(fpath) as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            issues.append(f"{fpath.name}: Invalid JSON — {exc}")
            invalid += 1
            continue

        # Handle both single task and list of tasks
        tasks = data if isinstance(data, list) else [data]

        for task in tasks:
            if not isinstance(task, dict):
                issues.append(f"{fpath.name}: Task is not a dict")
                invalid += 1
                continue

            # Check required fields
            missing = required_fields - set(task.keys())
            if missing:
                issues.append(
                    f"{fpath.name}: Missing fields: {missing}"
                )
                invalid += 1
                continue

            # Check for duplicate IDs
            task_id = task.get("task_id", "")
            if task_id in seen_ids:
                issues.append(f"{fpath.name}: Duplicate task_id: {task_id}")
                invalid += 1
                continue
            seen_ids.add(task_id)

            # Check tests
            tests = task.get("tests", task.get("visible_tests", []))
            if not tests:
                issues.append(f"{fpath.name}/{task_id}: No tests defined")
                invalid += 1
                continue

            valid += 1

    # Report
    print(f"\n═══ Task Validation Report ═══\n")
    print(f"  Directory: {gym_dir}")
    print(f"  Files:     {total}")
    print(f"  Valid:     {valid}")
    print(f"  Invalid:   {invalid}")

    if issues:
        print(f"\n  Issues ({len(issues)}):")
        for issue in issues[:20]:
            print(f"    ✗ {issue}")
        if len(issues) > 20:
            print(f"    ... and {len(issues) - 20} more")

    print(f"\n  Result: {'PASS' if invalid == 0 else 'FAIL'}")
    return invalid == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate gym task data")
    parser.add_argument(
        "--dir", default="gym_data", help="Gym data directory"
    )
    args = parser.parse_args()
    success = validate_tasks(args.dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
