"""Layer 8 — Download Benchmarks Script.

Download benchmark datasets (HumanEval, MBPP, LiveCodeBench) with
version verification (SHA-256 hashes).
~90 lines | Category: CLI
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import urllib.request
from typing import Any, Optional


# Benchmark dataset sources
BENCHMARK_SOURCES: dict[str, dict[str, str]] = {
    "humaneval": {
        "url": "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz",
        "filename": "humaneval.json",
        "description": "OpenAI HumanEval — 164 Python functions",
    },
    "mbpp": {
        "url": "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl",
        "filename": "mbpp.json",
        "description": "Google MBPP — 500 Python tasks",
    },
    "livecodebench": {
        "url": "",  # Rolling set — requires API access
        "filename": "livecodebench.json",
        "description": "LiveCodeBench — rolling competitive programming",
    },
    "swebench": {
        "url": "",  # Requires HuggingFace download
        "filename": "swebench.json",
        "description": "SWE-bench — real GitHub issues",
    },
}


def download_benchmarks(
    output_dir: str,
    db_path: Optional[str] = None,
    benchmarks: Optional[list[str]] = None,
) -> bool:
    """Download and verify benchmark datasets.

    Args:
        output_dir: Directory to save benchmark data.
        db_path: Database path for storing version hashes.
        benchmarks: Specific benchmarks to download (default: all).

    Returns True if all downloads succeed.
    """
    os.makedirs(output_dir, exist_ok=True)

    targets = benchmarks or list(BENCHMARK_SOURCES.keys())
    all_ok = True

    for name in targets:
        source = BENCHMARK_SOURCES.get(name)
        if source is None:
            print(f"  ✗ Unknown benchmark: {name}")
            all_ok = False
            continue

        output_path = os.path.join(output_dir, source["filename"])
        url = source["url"]

        if not url:
            print(f"  ⚠ {name}: Manual download required ({source['description']})")
            if os.path.exists(output_path):
                print(f"    ✓ Existing file found: {output_path}")
            else:
                print(f"    ✗ File not found: {output_path}")
            continue

        print(f"  Downloading {name}...")
        try:
            urllib.request.urlretrieve(url, output_path)
            print(f"    ✓ Saved: {output_path}")
        except Exception as exc:
            print(f"    ✗ Download failed: {exc}")
            all_ok = False
            continue

        # Compute and store hash
        file_hash = _compute_hash(output_path)
        print(f"    SHA-256: {file_hash[:16]}...")

        if db_path:
            _store_hash(db_path, name, file_hash)

    return all_ok


def verify_benchmarks(
    data_dir: str, db_path: str
) -> bool:
    """Verify benchmark files match stored hashes."""
    all_ok = True

    for name, source in BENCHMARK_SOURCES.items():
        fpath = os.path.join(data_dir, source["filename"])
        if not os.path.exists(fpath):
            continue

        actual = _compute_hash(fpath)
        stored = _get_stored_hash(db_path, name)

        if stored and actual != stored:
            print(f"  ✗ {name}: Hash mismatch")
            all_ok = False
        elif stored:
            print(f"  ✓ {name}: Hash verified")
        else:
            print(f"  ⚠ {name}: No stored hash (first download?)")

    return all_ok


def _compute_hash(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _store_hash(db_path: str, name: str, file_hash: str) -> None:
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS benchmark_versions "
            "(name TEXT PRIMARY KEY, hash TEXT, updated_at TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO benchmark_versions (name, hash, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (name, file_hash),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Non-critical


def _get_stored_hash(db_path: str, name: str) -> Optional[str]:
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT hash FROM benchmark_versions WHERE name = ?", (name,)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Download benchmark datasets")
    parser.add_argument(
        "--dir", default="benchmark_data", help="Output directory"
    )
    parser.add_argument("--db", default="data/system.db", help="Database path")
    parser.add_argument(
        "--benchmark",
        nargs="*",
        help="Specific benchmarks to download",
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Verify hashes only"
    )

    args = parser.parse_args()

    if args.verify_only:
        success = verify_benchmarks(args.dir, args.db)
    else:
        success = download_benchmarks(args.dir, args.db, args.benchmark)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
