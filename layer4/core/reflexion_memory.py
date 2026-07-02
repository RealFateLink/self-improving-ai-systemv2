"""reflexion_memory.py — Episodic memory for self-improving code AI.

Layer 4 — v0.2.0.  Implements Reflexion-style verbal reinforcement learning.
Stores failure/success narratives and injects them into prompts.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class MemoryEntry:
    """A single episodic memory entry."""
    entry_id: str
    cycle_number: int
    track_id: str
    task_id: str
    outcome: str  # "success" | "failure"
    narrative: str
    lessons: list[str]
    code_snippet: str = ""
    error_pattern: str = ""
    timestamp: str = ""


@dataclass
class ReflexionMemory:
    """Episodic memory system for self-reflection.

    Stores narratives of failures and successes, then injects relevant
    memories into generation prompts to improve future performance.
    """

    db_path: Path = field(default_factory=lambda: Path("layer0/data/meta_learning/reflexion.db"))
    max_entries: int = 1000
    similarity_threshold: float = 0.6

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    entry_id TEXT PRIMARY KEY,
                    cycle_number INTEGER NOT NULL,
                    track_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    lessons TEXT NOT NULL,
                    code_snippet TEXT DEFAULT '',
                    error_pattern TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_track ON memories(track_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error ON memories(error_pattern)
            """)
            conn.commit()

    def add_entry(
        self,
        cycle_number: int,
        track_id: str,
        task_id: str,
        outcome: str,
        narrative: str,
        lessons: list[str],
        code_snippet: str = "",
        error_pattern: str = "",
    ) -> None:
        entry = MemoryEntry(
            entry_id=f"mem_{cycle_number}_{task_id}",
            cycle_number=cycle_number,
            track_id=track_id,
            task_id=task_id,
            outcome=outcome,
            narrative=narrative,
            lessons=lessons,
            code_snippet=code_snippet,
            error_pattern=error_pattern,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO memories
                (entry_id, cycle_number, track_id, task_id, outcome, narrative, lessons, code_snippet, error_pattern, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.entry_id, entry.cycle_number, entry.track_id, entry.task_id,
                    entry.outcome, entry.narrative, json.dumps(entry.lessons),
                    entry.code_snippet, entry.error_pattern, entry.timestamp,
                ),
            )
            conn.commit()
        self._prune_old_entries()

    def _prune_old_entries(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if count > self.max_entries:
                to_delete = count - self.max_entries
                conn.execute(
                    f"DELETE FROM memories WHERE entry_id IN (SELECT entry_id FROM memories ORDER BY cycle_number ASC LIMIT {to_delete})"
                )
                conn.commit()

    def retrieve_relevant(
        self,
        task_description: str,
        track_id: str,
        limit: int = 3,
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories based on simple keyword matching.

        In production, replace with embedding-based similarity search.
        """
        keywords = set(task_description.lower().split())
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE track_id = ? ORDER BY cycle_number DESC LIMIT ?",
                (track_id, limit * 3),
            ).fetchall()

        scored = []
        for row in rows:
            narrative = row[5].lower()
            score = len(keywords & set(narrative.split()))
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, row in scored[:limit]:
            results.append(MemoryEntry(
                entry_id=row[0],
                cycle_number=row[1],
                track_id=row[2],
                task_id=row[3],
                outcome=row[4],
                narrative=row[5],
                lessons=json.loads(row[6]),
                code_snippet=row[7],
                error_pattern=row[8],
                timestamp=row[9],
            ))
        return results

    def format_memory_for_prompt(self, memories: list[MemoryEntry]) -> str:
        """Format memories into a prompt injection string."""
        if not memories:
            return ""
        lines = ["## Past Experiences (learn from these):"]
        for mem in memories:
            lines.append(f"\n### {mem.outcome.upper()} — Task: {mem.task_id}")
            lines.append(f"Narrative: {mem.narrative}")
            if mem.lessons:
                lines.append("Lessons learned:")
                for lesson in mem.lessons:
                    lines.append(f"  - {lesson}")
            if mem.code_snippet:
                lines.append(f"Relevant code pattern:\n```\n{mem.code_snippet[:500]}\n```")
        return "\n".join(lines)

    def get_failure_patterns(self, track_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get common failure patterns for a track."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """SELECT error_pattern, COUNT(*) as cnt, MAX(narrative) as example
                FROM memories
                WHERE track_id = ? AND outcome = 'failure' AND error_pattern != ''
                GROUP BY error_pattern
                ORDER BY cnt DESC
                LIMIT ?""",
                (track_id, limit),
            ).fetchall()
        return [
            {"pattern": row[0], "count": row[1], "example": row[2]}
            for row in rows
        ]

    def get_stats(self) -> dict[str, Any]:
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM memories WHERE outcome = 'success'").fetchone()[0]
            failures = conn.execute("SELECT COUNT(*) FROM memories WHERE outcome = 'failure'").fetchone()[0]
        return {
            "total_entries": total,
            "successes": successes,
            "failures": failures,
        }
