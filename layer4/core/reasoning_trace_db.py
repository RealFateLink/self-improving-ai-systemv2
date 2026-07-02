"""
Reasoning Trace Database
Stores generation history, reasoning chains, and outcomes.
Pre-formats successful traces into SFT/GRPO training datasets.
"""
import sqlite3
import json
import hashlib
import os
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class ReasoningTrace:
    id: int
    problem_id: str
    language: str
    system_prompt_hash: str
    reasoning_text: str
    generated_code: str
    tests_passed: bool
    error_message: Optional[str]
    skill_ids: List[str]
    strategy_ids: List[str]
    repair_ids: List[str]
    model_backend: str
    temperature: float
    tokens_total: int
    cost_usd: float
    created_at: str


class ReasoningTraceDB:
    def __init__(self, db_path: str = "layer0/data/meta_learning/reasoning_traces.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS reasoning_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id TEXT NOT NULL,
            language TEXT NOT NULL,
            system_prompt TEXT,
            system_prompt_hash TEXT,
            user_prompt TEXT,
            reasoning_text TEXT,
            generated_code TEXT,
            tests_passed INTEGER,
            execution_output TEXT,
            error_message TEXT,
            skill_ids TEXT,
            strategy_ids TEXT,
            repair_ids TEXT,
            model_backend TEXT,
            temperature REAL,
            tokens_prompt INTEGER,
            tokens_completion INTEGER,
            estimated_cost_usd REAL,
            created_at TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS trace_reviews (
            trace_id INTEGER PRIMARY KEY,
            helpful INTEGER,
            human_corrected_code TEXT,
            human_corrected_reasoning TEXT,
            reviewer_notes TEXT,
            reviewed_at TEXT,
            FOREIGN KEY(trace_id) REFERENCES reasoning_traces(id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS prompt_versions (
            hash TEXT PRIMARY KEY,
            system_prompt TEXT,
            use_count INTEGER DEFAULT 0,
            avg_success_rate REAL DEFAULT 0.0,
            first_used TEXT,
            last_used TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS training_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id INTEGER,
            export_format TEXT,
            input_text TEXT,
            output_text TEXT,
            reward_score REAL,
            exported_at TEXT,
            FOREIGN KEY(trace_id) REFERENCES reasoning_traces(id)
        )''')

        c.execute('''CREATE INDEX IF NOT EXISTS idx_traces_problem ON reasoning_traces(problem_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_traces_success ON reasoning_traces(tests_passed)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_traces_lang ON reasoning_traces(language)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_traces_time ON reasoning_traces(created_at)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_traces_hash ON reasoning_traces(system_prompt_hash)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_examples_format ON training_examples(export_format)''')

        conn.commit()
        conn.close()

    def _hash_prompt(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def store_trace(self,
                    problem_id: str,
                    language: str,
                    system_prompt: str,
                    user_prompt: str,
                    reasoning_text: str,
                    generated_code: str,
                    tests_passed: bool,
                    execution_output: Optional[str] = None,
                    error_message: Optional[str] = None,
                    skill_ids: Optional[List[str]] = None,
                    strategy_ids: Optional[List[str]] = None,
                    repair_ids: Optional[List[str]] = None,
                    model_backend: str = "unknown",
                    temperature: float = 0.7,
                    tokens_prompt: int = 0,
                    tokens_completion: int = 0,
                    estimated_cost_usd: float = 0.0) -> int:
        now = datetime.now().isoformat()
        prompt_hash = self._hash_prompt(system_prompt)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''INSERT INTO reasoning_traces
            (problem_id, language, system_prompt, system_prompt_hash, user_prompt,
             reasoning_text, generated_code, tests_passed, execution_output, error_message,
             skill_ids, strategy_ids, repair_ids, model_backend, temperature,
             tokens_prompt, tokens_completion, estimated_cost_usd, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (problem_id, language, system_prompt, prompt_hash, user_prompt,
             reasoning_text, generated_code, int(tests_passed), execution_output, error_message,
             json.dumps(skill_ids or []), json.dumps(strategy_ids or []), json.dumps(repair_ids or []),
             model_backend, temperature, tokens_prompt, tokens_completion, estimated_cost_usd, now))

        trace_id = c.lastrowid

        c.execute('''INSERT INTO prompt_versions (hash, system_prompt, use_count, avg_success_rate, first_used, last_used)
                     VALUES (?,?,1,?,?,?)
                     ON CONFLICT(hash) DO UPDATE SET
                     use_count = use_count + 1,
                     avg_success_rate = ((avg_success_rate * use_count) + ?) / (use_count + 1),
                     last_used = ?''',
                     (prompt_hash, system_prompt[:500], 1.0 if tests_passed else 0.0, now, now,
                      1.0 if tests_passed else 0.0, now))

        conn.commit()
        conn.close()
        return trace_id

    def add_human_review(self, trace_id: int, helpful: Optional[bool] = None,
                         corrected_code: Optional[str] = None,
                         corrected_reasoning: Optional[str] = None,
                         notes: Optional[str] = None):
        now = datetime.now().isoformat()
        val = 1 if helpful is True else (0 if helpful is False else None)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO trace_reviews
            (trace_id, helpful, human_corrected_code, human_corrected_reasoning, reviewer_notes, reviewed_at)
            VALUES (?,?,?,?,?,?)''',
            (trace_id, val, corrected_code, corrected_reasoning, notes, now))
        conn.commit()
        conn.close()

    def generate_training_exports(self, min_reward_threshold: float = 0.7,
                                   language: str = "python",
                                   batch_size: int = 500) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''SELECT id, system_prompt, user_prompt, reasoning_text, generated_code,
                            tests_passed, skill_ids, execution_output, tokens_completion
                     FROM reasoning_traces
                     WHERE language = ?
                     AND tests_passed = 1
                     AND reasoning_text IS NOT NULL
                     AND length(reasoning_text) > 10
                     AND id NOT IN (
                         SELECT trace_id FROM training_examples
                         WHERE export_format = 'sft' AND trace_id IS NOT NULL
                     )
                     ORDER BY created_at DESC
                     LIMIT ?''', (language, batch_size))
        rows = c.fetchall()

        count = 0
        now = datetime.now().isoformat()

        for row in rows:
            tid, sys_p, user_p, reasoning, code, passed, skills_json, exec_out, tokens = row
            skills = json.loads(skills_json or '[]')

            reward = 1.0
            reward += min(len(skills) * 0.05, 0.25)
            reward -= min((tokens or 0) / 4000, 0.2)
            if error_str := str(exec_out or "").lower():
                if any(w in error_str for w in ["warning", "deprecat", "slow"]):
                    reward -= 0.1

            if reward < min_reward_threshold:
                continue

            input_text = f"{sys_p}\n\n{user_p}"
            output_text = f"REASONING:\n{reasoning}\n\nCODE:\n```\n{code}\n```"

            c.execute('''INSERT INTO training_examples
                (trace_id, export_format, input_text, output_text, reward_score, exported_at)
                VALUES (?,?,?,?,?,?)''',
                (tid, 'sft', input_text, output_text, round(reward, 4), now))

            c.execute('''INSERT INTO training_examples
                (trace_id, export_format, input_text, output_text, reward_score, exported_at)
                VALUES (?,?,?,?,?,?)''',
                (tid, 'grpo', input_text, output_text, round(reward, 4), now))
            count += 1

        conn.commit()
        conn.close()
        return count

    def get_training_dataset(self, export_format: str = "sft",
                              min_reward: float = 0.8,
                              language: Optional[str] = None,
                              limit: int = 10000) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        if language:
            c.execute('''SELECT t.id, t.system_prompt, t.user_prompt, t.reasoning_text,
                                t.generated_code, te.reward_score
                         FROM reasoning_traces t
                         JOIN training_examples te ON t.id = te.trace_id
                         WHERE te.export_format = ?
                         AND te.reward_score >= ?
                         AND t.language = ?
                         AND (t.id IN (SELECT trace_id FROM trace_reviews WHERE helpful = 1)
                              OR t.tests_passed = 1)
                         ORDER BY te.reward_score DESC
                         LIMIT ?''', (export_format, min_reward, language, limit))
        else:
            c.execute('''SELECT t.id, t.system_prompt, t.user_prompt, t.reasoning_text,
                                t.generated_code, te.reward_score
                         FROM reasoning_traces t
                         JOIN training_examples te ON t.id = te.trace_id
                         WHERE te.export_format = ?
                         AND te.reward_score >= ?
                         AND (t.id IN (SELECT trace_id FROM trace_reviews WHERE helpful = 1)
                              OR t.tests_passed = 1)
                         ORDER BY te.reward_score DESC
                         LIMIT ?''', (export_format, min_reward, limit))

        rows = c.fetchall()
        conn.close()

        dataset = []
        for row in rows:
            tid, sys_p, user_p, reasoning, code, reward = row
            dataset.append({
                "trace_id": tid,
                "prompt": f"{sys_p}\n\n{user_p}",
                "completion": f"REASONING:\n{reasoning}\n\nCODE:\n```\n{code}\n```",
                "reward": reward
            })
        return dataset

    def get_prompt_ab_test_results(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''SELECT hash, use_count, avg_success_rate, first_used, last_used
                     FROM prompt_versions
                     WHERE use_count > 5
                     ORDER BY avg_success_rate DESC''')
        rows = c.fetchall()
        conn.close()
        return [{
            "hash": r[0],
            "uses": r[1],
            "success_rate": round(r[2], 3),
            "first": r[3],
            "last": r[4]
        } for r in rows]

    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT COUNT(*), SUM(tests_passed), AVG(estimated_cost_usd) FROM reasoning_traces")
        total, passed, avg_cost = c.fetchone()

        c.execute("SELECT COUNT(*) FROM trace_reviews WHERE helpful = 1")
        human_good = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM training_examples WHERE export_format = 'sft'")
        sft_ready = c.fetchone()[0]

        c.execute("SELECT model_backend, COUNT(*) FROM reasoning_traces GROUP BY model_backend")
        backends = {r[0]: r[1] for r in c.fetchall()}

        conn.close()
        return {
            "total_traces": total,
            "success_rate": round((passed or 0) / max(total, 1), 3),
            "avg_cost_usd": round(avg_cost or 0, 4),
            "human_reviewed_good": human_good,
            "sft_examples_ready": sft_ready,
            "backends": backends,
            "training_ready": (sft_ready or 0) > 100
        }
