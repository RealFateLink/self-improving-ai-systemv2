"""
Skill-Based Curriculum Selector
Queries the problem corpus using skill tags to enable deliberate practice.
"""
import sqlite3
import json
import random
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta


class SkillCurriculumSelector:
    def __init__(self,
                 problems_db_path: str = "layer0/data/meta_learning/problems.db",
                 skill_ontology_db_path: str = "layer0/data/meta_learning/skills.db"):
        self.problems_db = problems_db_path
        self.skill_db = skill_ontology_db_path
        os.makedirs(os.path.dirname(problems_db_path), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS problems (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            difficulty TEXT,
            language TEXT,
            problem_type TEXT,
            estimated_time_minutes INTEGER,
            source TEXT,
            created_at TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS problem_skill_tags (
            problem_id TEXT,
            skill_id TEXT,
            is_primary INTEGER,
            required_mastery REAL,
            FOREIGN KEY(problem_id) REFERENCES problems(id),
            PRIMARY KEY(problem_id, skill_id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS problem_attempts (
            problem_id TEXT,
            trace_id INTEGER,
            passed INTEGER,
            attempted_at TEXT,
            PRIMARY KEY(problem_id, trace_id)
        )''')

        c.execute('''CREATE INDEX IF NOT EXISTS idx_tags_skill ON problem_skill_tags(skill_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_attempts_problem ON problem_attempts(problem_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_attempts_time ON problem_attempts(attempted_at)''')

        conn.commit()
        conn.close()

    def add_problem(self, problem_id: str, title: str, description: str,
                    difficulty: str, language: str, problem_type: str,
                    skill_tags: List[Dict], estimated_time: int = 30,
                    source: str = "human"):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()

        c.execute('''INSERT OR REPLACE INTO problems
            (id, title, description, difficulty, language, problem_type,
             estimated_time_minutes, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (problem_id, title, description, difficulty, language, problem_type,
             estimated_time, source, now))

        c.execute("DELETE FROM problem_skill_tags WHERE problem_id = ?", (problem_id,))
        for tag in skill_tags:
            c.execute('''INSERT INTO problem_skill_tags
                (problem_id, skill_id, is_primary, required_mastery)
                VALUES (?,?,?,?)''',
                (problem_id, tag["skill_id"],
                 1 if tag.get("is_primary") else 0,
                 tag.get("required_mastery", 0.0)))

        conn.commit()
        conn.close()

    def select_next_problem(self, recommendation: Dict,
                           language: str = "python",
                           recent_problem_ids: Optional[List[str]] = None) -> Optional[Dict]:
        rec_type = recommendation.get("recommendation", "deliberate_practice")
        focus_skills = recommendation.get("focus_skills", [])
        focus_ids = [s["id"] for s in focus_skills]

        if not focus_ids:
            return self._select_fresh_problem(language, exclude=recent_problem_ids)

        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        placeholders = ','.join('?' * len(focus_ids))

        if rec_type == "drill_prerequisites":
            c.execute(f'''
                SELECT p.*, GROUP_CONCAT(pst.skill_id) as skill_set
                FROM problems p
                JOIN problem_skill_tags pst ON p.id = pst.problem_id
                WHERE p.language = ?
                AND pst.skill_id IN ({placeholders})
                AND pst.is_primary = 1
                AND p.difficulty IN ('easy', 'medium')
                AND p.id NOT IN (
                    SELECT problem_id FROM problem_attempts
                    WHERE passed = 1
                    AND attempted_at > datetime('now', '-1 day')
                )
                GROUP BY p.id
                ORDER BY p.difficulty, RANDOM()
                LIMIT 10
            ''', (language, *focus_ids))

        else:  # deliberate_practice
            c.execute(f'''
                SELECT p.*, GROUP_CONCAT(pst.skill_id) as skill_set,
                       COUNT(DISTINCT pst.skill_id) as skill_count
                FROM problems p
                JOIN problem_skill_tags pst ON p.id = pst.problem_id
                WHERE p.language = ?
                AND p.id IN (
                    SELECT problem_id FROM problem_skill_tags
                    WHERE skill_id IN ({placeholders})
                )
                AND p.difficulty IN ('medium', 'hard')
                AND p.id NOT IN (
                    SELECT problem_id FROM problem_attempts
                    WHERE passed = 1
                    AND attempted_at > datetime('now', '-3 days')
                )
                GROUP BY p.id
                HAVING skill_count BETWEEN 2 AND 6
                ORDER BY RANDOM()
                LIMIT 10
            ''', (language, *focus_ids))

        rows = c.fetchall()
        conn.close()

        candidates = []
        for row in rows:
            d = self._row_to_dict(row)
            d["skill_set"] = row[9].split(",") if len(row) > 9 and row[9] else []
            candidates.append(d)

        if recent_problem_ids:
            candidates = [cand for cand in candidates if cand["id"] not in recent_problem_ids]

        if not candidates:
            return self._select_by_skill_overlap(focus_ids, language, exclude=recent_problem_ids)

        unsolved = [cand for cand in candidates if not self._was_solved_ever(cand["id"])]
        if unsolved:
            return random.choice(unsolved)

        return random.choice(candidates)

    def _select_fresh_problem(self, language: str,
                               exclude: Optional[List[str]] = None) -> Optional[Dict]:
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        c.execute('''
            SELECT p.*, '' as skill_set
            FROM problems p
            WHERE p.language = ?
            AND p.id NOT IN (SELECT problem_id FROM problem_attempts WHERE passed = 1)
            AND p.id NOT IN (
                SELECT problem_id FROM problem_attempts
                WHERE attempted_at > datetime('now', '-12 hours')
            )
            ORDER BY RANDOM()
            LIMIT 1
        ''', (language,))
        row = c.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def _select_by_skill_overlap(self, skill_ids: List[str], language: str,
                                  exclude: Optional[List[str]] = None) -> Optional[Dict]:
        if not skill_ids:
            return None
        placeholders = ','.join('?' * len(skill_ids))
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        c.execute(f'''
            SELECT p.*, COUNT(DISTINCT pst.skill_id) as overlap
            FROM problems p
            JOIN problem_skill_tags pst ON p.id = pst.problem_id
            WHERE p.language = ?
            AND pst.skill_id IN ({placeholders})
            GROUP BY p.id
            ORDER BY overlap DESC, RANDOM()
            LIMIT 1
        ''', (language, *skill_ids))
        row = c.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def _was_solved_ever(self, problem_id: str) -> bool:
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        c.execute('''SELECT COUNT(*) FROM problem_attempts
                     WHERE problem_id = ? AND passed = 1''', (problem_id,))
        result = c.fetchone()[0] > 0
        conn.close()
        return result

    def record_attempt(self, problem_id: str, trace_id: int, passed: bool):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO problem_attempts
                       (problem_id, trace_id, passed, attempted_at)
                       VALUES (?,?,?,?)''',
                  (problem_id, trace_id, int(passed), now))
        conn.commit()
        conn.close()

    def get_problem_analytics(self, problem_id: str) -> Dict:
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        c.execute('''SELECT COUNT(*), SUM(passed) FROM problem_attempts
                     WHERE problem_id = ?''', (problem_id,))
        total, passed = c.fetchone()
        conn.close()
        return {
            "attempts": total or 0,
            "passes": passed or 0,
            "pass_rate": round((passed or 0) / max(total, 1), 2)
        }

    def get_curriculum_stats(self) -> Dict:
        conn = sqlite3.connect(self.problems_db)
        c = conn.cursor()
        c.execute('''SELECT COUNT(DISTINCT problem_id),
                            SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END)
                     FROM problem_attempts''')
        total_attempted, total_passed = c.fetchone()
        c.execute("SELECT COUNT(*) FROM problems")
        total_problems = c.fetchone()[0]
        conn.close()
        return {
            "total_problems": total_problems,
            "attempted": total_attempted or 0,
            "passed": total_passed or 0,
            "coverage": round((total_attempted or 0) / max(total_problems, 1), 2)
        }

    def seed_sample_problems(self):
        samples = [
            {
                "id": "py_sum_list",
                "title": "Sum of List",
                "description": "Write a function sum_list(nums) that returns the sum of integers.",
                "difficulty": "easy", "language": "python", "type": "algorithm",
                "skills": [
                    {"skill_id": "py_var", "is_primary": True, "required_mastery": 0.0},
                    {"skill_id": "py_loop", "is_primary": True, "required_mastery": 0.0}
                ]
            },
            {
                "id": "py_count_words",
                "title": "Word Frequency",
                "description": "Count word occurrences in a string using a dictionary.",
                "difficulty": "easy", "language": "python", "type": "algorithm",
                "skills": [
                    {"skill_id": "py_dict", "is_primary": True, "required_mastery": 0.1},
                    {"skill_id": "py_loop", "is_primary": False, "required_mastery": 0.0}
                ]
            },
            {
                "id": "py_log_parser",
                "title": "Log Parser",
                "description": "Read a log file, extract ERROR lines with regex, count by hour.",
                "difficulty": "medium", "language": "python", "type": "io",
                "skills": [
                    {"skill_id": "py_io", "is_primary": True, "required_mastery": 0.2},
                    {"skill_id": "py_re", "is_primary": True, "required_mastery": 0.2},
                    {"skill_id": "py_dict", "is_primary": False, "required_mastery": 0.1}
                ]
            },
            {
                "id": "py_tree_depth",
                "title": "Maximum Tree Depth",
                "description": "Calculate max depth of a binary tree using recursion.",
                "difficulty": "medium", "language": "python", "type": "algorithm",
                "skills": [
                    {"skill_id": "py_rec", "is_primary": True, "required_mastery": 0.3},
                    {"skill_id": "py_dsa_tree", "is_primary": True, "required_mastery": 0.2}
                ]
            },
            {
                "id": "py_climbing_stairs",
                "title": "Climbing Stairs",
                "description": "Classic DP: count ways to climb n stairs taking 1 or 2 steps.",
                "difficulty": "hard", "language": "python", "type": "algorithm",
                "skills": [
                    {"skill_id": "py_dp", "is_primary": True, "required_mastery": 0.5},
                    {"skill_id": "py_rec", "is_primary": False, "required_mastery": 0.4}
                ]
            },
            {
                "id": "py_api_client",
                "title": "REST API Client",
                "description": "Fetch JSON from an API, handle timeouts and parse nested fields.",
                "difficulty": "medium", "language": "python", "type": "io",
                "skills": [
                    {"skill_id": "py_api", "is_primary": True, "required_mastery": 0.3},
                    {"skill_id": "py_err", "is_primary": True, "required_mastery": 0.2},
                    {"skill_id": "py_dict", "is_primary": False, "required_mastery": 0.1}
                ]
            },
            {
                "id": "py_async_fetcher",
                "title": "Async URL Fetcher",
                "description": "Fetch 10 URLs concurrently using asyncio and aiohttp.",
                "difficulty": "hard", "language": "python", "type": "system_design",
                "skills": [
                    {"skill_id": "py_async", "is_primary": True, "required_mastery": 0.5},
                    {"skill_id": "py_api", "is_primary": False, "required_mastery": 0.4},
                    {"skill_id": "py_err", "is_primary": False, "required_mastery": 0.3}
                ]
            }
        ]

        for s in samples:
            self.add_problem(
                s["id"], s["title"], s["description"],
                s["difficulty"], s["language"], s["type"],
                s["skills"]
            )

    def _row_to_dict(self, row) -> Dict:
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "difficulty": row[3],
            "language": row[4],
            "problem_type": row[5],
            "estimated_time_minutes": row[6],
            "source": row[7],
            "created_at": row[8]
        }
