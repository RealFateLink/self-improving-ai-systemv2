"""
Repair Strategy Memory
Learns bug types and their fixes from debugging episodes.
"""
import sqlite3
import json
import os
import difflib
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class RepairPattern:
    id: str
    bug_type: str
    symptom_pattern: str
    fix_pattern: str
    skill_ids: List[str]
    language: str
    success_count: int
    failure_count: int
    example_before: str
    example_after: str
    created_at: str


class RepairStrategyMemory:
    def __init__(self, db_path: str = "layer0/data/meta_learning/repairs.db", llm_client=None):
        self.db_path = db_path
        self.llm = llm_client
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS repairs (
            id TEXT PRIMARY KEY,
            bug_type TEXT,
            symptom_pattern TEXT,
            fix_pattern TEXT,
            skill_ids TEXT,
            language TEXT,
            success_count INTEGER,
            failure_count INTEGER,
            example_before TEXT,
            example_after TEXT,
            created_at TEXT
        )''')
        conn.commit()
        conn.close()

    def _extract_diff_summary(self, before: str, after: str) -> str:
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm=''))
        return "\n".join([l for l in diff if l.startswith('+ ') or l.startswith('- ')][:20])

    def extract_repair(self, buggy_code: str, fixed_code: str, error_message: str,
                       skill_ids: List[str], language: str = "python") -> Optional[RepairPattern]:
        if not self.llm:
            return None

        diff_summary = self._extract_diff_summary(buggy_code, fixed_code)

        prompt = f"""Classify this bug and abstract the repair strategy.

Error: {error_message[:300]}

Changes:
{diff_summary}

Return ONLY JSON:
{{"bug_type": "short category", "symptom": "how to recognize this", "fix": "abstract fix pattern"}}"""

        try:
            response = self.llm.complete(prompt, system="You are a debugging expert.", temperature=0.2)
            result = json.loads(response.strip())

            rid = f"repair_{datetime.now().strftime('%Y%m%d%H%M%S')}_{buggy_code[:8].encode().hex()}"
            now = datetime.now().isoformat()

            pattern = RepairPattern(
                id=rid, bug_type=result.get("bug_type", "unknown"),
                symptom_pattern=result.get("symptom", ""),
                fix_pattern=result.get("fix", ""),
                skill_ids=skill_ids, language=language,
                success_count=1, failure_count=0,
                example_before=buggy_code[:500],
                example_after=fixed_code[:500],
                created_at=now
            )

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO repairs VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                     (rid, pattern.bug_type, pattern.symptom_pattern, pattern.fix_pattern,
                      json.dumps(skill_ids), language, 1, 0,
                      pattern.example_before, pattern.example_after, now))
            conn.commit()
            conn.close()
            return pattern
        except Exception as e:
            print(f"[RepairMemory] Extraction failed: {e}")
            return None

    def diagnose(self, code: str, error_message: str,
                 skill_ids: List[str], language: str = "python") -> List[RepairPattern]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM repairs WHERE language IN (?, 'language_agnostic')", (language,))
        rows = c.fetchall()
        conn.close()

        candidates = []
        err_lower = error_message.lower()

        for row in rows:
            bug_type = row[1]
            symptom = row[2]
            stored_skills = json.loads(row[4])

            sym_words = set(symptom.lower().split()) if symptom else set()
            err_words = set(err_lower.split())
            symptom_score = len(sym_words & err_words) / max(len(sym_words), 1) if sym_words else 0.0

            type_score = 1.0 if bug_type.lower() in err_lower else 0.0

            overlap = len(set(stored_skills) & set(skill_ids))
            skill_score = overlap / max(len(stored_skills), len(skill_ids), 1)

            total = row[6] + row[7]
            success_rate = row[6] / max(total, 1)

            score = symptom_score * 0.4 + type_score * 0.3 + skill_score * 0.2 + success_rate * 0.1
            if score > 0.1:
                candidates.append((score, row))

        candidates.sort(reverse=True)

        patterns = []
        for score, row in candidates[:3]:
            patterns.append(RepairPattern(
                id=row[0], bug_type=row[1], symptom_pattern=row[2], fix_pattern=row[3],
                skill_ids=json.loads(row[4]), language=row[5], success_count=row[6],
                failure_count=row[7], example_before=row[8], example_after=row[9],
                created_at=row[10]
            ))
        return patterns

    def record_success(self, repair_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE repairs SET success_count = success_count + 1 WHERE id = ?", (repair_id,))
        conn.commit()
        conn.close()

    def record_failure(self, repair_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE repairs SET failure_count = failure_count + 1 WHERE id = ?", (repair_id,))
        conn.commit()
        conn.close()
