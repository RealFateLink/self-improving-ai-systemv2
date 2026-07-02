"""Layer 8 — Bootstrap Script.

First-time setup: schema creation, invariant hash generation, sequence
initialization, dependency check. Run once before the system starts.
~210 lines | Category: CLI
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
REQUIRED_PYTHON_VERSION = (3, 11)

REQUIRED_TEMPLATES = [
    "intent_interpreter.yaml",
    "curriculum_sampler.yaml",
    "planner.yaml",
    "generator.yaml",
    "static_reviewer.yaml",
    "dynamic_verifier.yaml",
    "semantic_critic.yaml",
    "selector.yaml",
    "optimization_specialist.yaml",
    "promotion_manager.yaml",
    "failure_narrator.yaml",
    "failure_narrator_anonymous.yaml",
    "reasoning_analyzer.yaml",
    "root_cause_detector.yaml",
    "counterfactual.yaml",
    "predictor.yaml",
    "success_analyzer.yaml",
    "strategy_learner.yaml",
    "meta_learner.yaml",
]

# Files whose hashes are checked at runtime (must not change)
INVARIANT_FILES = [
    "src/result.py",
    "src/types/enums.py",
    "src/layer1/invariants.py",
    "src/layer1/validators.py",
]

# ID prefixes for the sequences table
SEQUENCE_PREFIXES = {
    "cycle": "CYC",
    "task": "TSK",
    "pattern": "PAT",
    "prediction_rule": "PRD",
    "strategy_version": "STR",
    "approval_item": "APR",
    "alert": "ALT",
    "agent": "AGT",
    "benchmark_session": "BMS",
    "cost_event": "CST",
}


def bootstrap(
    db_path: str,
    schema_path: str = "schema/schema.sql",
    config_dir: str = "config",
    template_dir: str = "templates",
    verify_only: bool = False,
) -> bool:
    """Run the full bootstrap process.

    Args:
        db_path: Path to the SQLite database file.
        schema_path: Path to schema.sql.
        config_dir: Path to config directory.
        template_dir: Path to templates directory.
        verify_only: If True, check without modifying.

    Returns True if all checks pass.
    """
    print(f"{'Verifying' if verify_only else 'Bootstrapping'} system...")
    all_ok = True

    # 1. Check Python version
    if sys.version_info < REQUIRED_PYTHON_VERSION:
        print(
            f"  ✗ Python {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}+ "
            f"required, found {sys.version_info.major}.{sys.version_info.minor}"
        )
        all_ok = False
    else:
        print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}")

    # 2. Check schema file exists
    if not os.path.exists(schema_path):
        print(f"  ✗ Schema file not found: {schema_path}")
        all_ok = False
    else:
        print(f"  ✓ Schema file: {schema_path}")

    # 3. Create database from schema
    if not verify_only:
        try:
            conn = sqlite3.connect(db_path)
            with open(schema_path) as f:
                conn.executescript(f.read())
            print(f"  ✓ Database created: {db_path}")
        except Exception as exc:
            print(f"  ✗ Database creation failed: {exc}")
            all_ok = False
            conn = None
    else:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            print(f"  ✓ Database exists: {db_path}")
        else:
            print(f"  ✗ Database not found: {db_path}")
            all_ok = False
            conn = None

    # 4. Initialize sequences
    if conn and not verify_only:
        try:
            _initialize_sequences(conn)
            print(f"  ✓ Sequences initialized ({len(SEQUENCE_PREFIXES)} prefixes)")
        except Exception as exc:
            print(f"  ✗ Sequence initialization failed: {exc}")
            all_ok = False

    # 5. Compute and store invariant hashes
    if conn and not verify_only:
        try:
            hashes = _compute_invariant_hashes()
            _store_invariant_hashes(conn, hashes)
            print(f"  ✓ Invariant hashes stored ({len(hashes)} files)")
        except Exception as exc:
            print(f"  ✗ Invariant hash generation failed: {exc}")
            all_ok = False
    elif conn:
        # Verify hashes
        hashes = _compute_invariant_hashes()
        stored = _get_stored_hashes(conn)
        mismatches = [
            f for f in hashes if stored.get(f) != hashes[f]
        ]
        if mismatches:
            print(f"  ✗ Invariant hash mismatches: {mismatches}")
            all_ok = False
        else:
            print(f"  ✓ Invariant hashes verified ({len(hashes)} files)")

    # 6. Record schema version
    if conn and not verify_only:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.commit()
            print(f"  ✓ Schema version: {SCHEMA_VERSION}")
        except Exception as exc:
            print(f"  ✗ Schema version recording failed: {exc}")
            all_ok = False

    # 7. Validate config files
    config_ok = _validate_config(config_dir)
    if not config_ok:
        all_ok = False

    # 8. Validate templates
    template_ok = _validate_templates(template_dir)
    if not template_ok:
        all_ok = False

    if conn:
        conn.close()

    status = "PASS" if all_ok else "FAIL"
    print(f"\nBootstrap {'verification' if verify_only else 'setup'}: {status}")
    return all_ok


def _initialize_sequences(conn: sqlite3.Connection) -> None:
    """Initialize sequence table with ID prefixes."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sequences "
        "(prefix TEXT PRIMARY KEY, next_value INTEGER DEFAULT 1)"
    )
    for name, prefix in SEQUENCE_PREFIXES.items():
        conn.execute(
            "INSERT OR IGNORE INTO sequences (prefix, next_value) VALUES (?, 1)",
            (prefix,),
        )
    conn.commit()


def _compute_invariant_hashes() -> dict[str, str]:
    """Compute SHA-256 hashes of invariant files."""
    hashes: dict[str, str] = {}
    for fpath in INVARIANT_FILES:
        if os.path.exists(fpath):
            sha = hashlib.sha256()
            with open(fpath, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            hashes[fpath] = sha.hexdigest()
    return hashes


def _store_invariant_hashes(
    conn: sqlite3.Connection, hashes: dict[str, str]
) -> None:
    """Store invariant hashes in system_state."""
    conn.execute(
        "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
        ("invariant_hashes", json.dumps(hashes)),
    )
    conn.commit()


def _get_stored_hashes(conn: sqlite3.Connection) -> dict[str, str]:
    """Retrieve stored invariant hashes."""
    try:
        row = conn.execute(
            "SELECT value FROM system_state WHERE key = 'invariant_hashes'"
        ).fetchone()
        return json.loads(row[0]) if row else {}
    except Exception:
        return {}


def _validate_config(config_dir: str) -> bool:
    """Validate config files exist and parse correctly."""
    required = ["system_config.yaml", "cost_config.yaml", "llm_config.yaml"]
    all_ok = True

    for fname in required:
        fpath = os.path.join(config_dir, fname)
        if not os.path.exists(fpath):
            print(f"  ✗ Config missing: {fpath}")
            all_ok = False
        else:
            # Try to parse YAML
            try:
                with open(fpath) as f:
                    content = f.read()
                if not content.strip():
                    print(f"  ✗ Config empty: {fpath}")
                    all_ok = False
                else:
                    print(f"  ✓ Config: {fname}")
            except Exception as exc:
                print(f"  ✗ Config parse error ({fname}): {exc}")
                all_ok = False

    return all_ok


def _validate_templates(template_dir: str) -> bool:
    """Validate required prompt templates exist."""
    all_ok = True
    found = 0
    missing = 0

    for tname in REQUIRED_TEMPLATES:
        fpath = os.path.join(template_dir, tname)
        if not os.path.exists(fpath):
            print(f"  ✗ Template missing: {tname}")
            missing += 1
            all_ok = False
        else:
            found += 1

    if found > 0:
        print(f"  ✓ Templates: {found}/{len(REQUIRED_TEMPLATES)} found")
    if missing > 0:
        print(f"  ✗ Templates: {missing} missing")

    return all_ok


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Bootstrap the AI system")
    parser.add_argument("--db", default="data/system.db", help="Database path")
    parser.add_argument(
        "--schema", default="schema/schema.sql", help="Schema path"
    )
    parser.add_argument("--config", default="config", help="Config directory")
    parser.add_argument(
        "--templates", default="templates", help="Template directory"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Check without modifying",
    )

    args = parser.parse_args()
    success = bootstrap(
        db_path=args.db,
        schema_path=args.schema,
        config_dir=args.config,
        template_dir=args.templates,
        verify_only=args.verify_only,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
