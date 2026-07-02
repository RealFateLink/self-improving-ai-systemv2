"""
Strategy Memory
Extracts and retrieves abstract problem-solving strategies.
"""
import sqlite3
import json
import os
import hashlib
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class Strategy:
    id: str
    skill_ids: List[str]
    context: str
    strategy_text: str
    language: str
    success_count: int
    failure_count: int
    avg_code_complexity: float
    created_at: str
    last_used: str


class StrategyMemory:
    def __init__(self, db_path: str = "layer0/data/meta_learning/strategies.db", llm_client=None):
        self.db_path = db_path
        self.llm = llm_client
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            skill_ids TEXT,
            context TEXT,
            strategy_text TEXT,
            language TEXT,
            success_count INTEGER,
            failure_count INTEGER,
            avg_code_complexity REAL,
            created_at TEXT,
            last_used TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS strategy_embeddings (
            strategy_id TEXT PRIMARY KEY,
            embedding TEXT,
            strategy_text_hash TEXT
        )''')
        conn.commit()
        conn.close()

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def _simple_embedding(self, text: str, dim: int = 128) -> List[float]:
        """
        Character n-gram projection. No external model required.
        """
        vec = [0.0] * dim
        text = text.lower()
        for i in range(len(text) - 2):
            tri = text[i:i+3]
            idx = hash(tri) % dim
            vec[idx] += 1.0
        norm = sum(x*x for x in vec) ** 0.5
        return [x/norm for x in vec] if norm > 0 else vec

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        return sum(x*y for x, y in zip(a, b))

    def extract_strategy(self, problem_text: str, solution_code: str,
                         skill_ids: List[str], language: str = "python") -> Optional[Strategy]:
        if not self.llm:
            return None

        prompt = f"""Analyze this successful coding solution and extract the CORE STRATEGY as a general heuristic.

Problem: {problem_text[:600]}

Solution: {solution_code[:800]}

Skills: {', '.join(skill_ids)}

Return ONLY JSON:
{{"context": "category", "strategy": "1-3 sentences describing the abstract approach"}}"""

        try:
            response = self.llm.complete(prompt, system="Extract reusable programming wisdom.", temperature=0.3)
            result = json.loads(response.strip())

            sid = f"strat_{self._hash(problem_text + solution_code)[:12]}"
            now = datetime.now().isoformat()
            strategy = Strategy(
                id=sid, skill_ids=skill_ids, context=result.get("context", "general"),
                strategy_text=result.get("strategy", "No strategy extracted."),
                language=language, success_count=1, failure_count=0,
                avg_code_complexity=1.0, created_at=now, last_used=now
            )

            emb = self._simple_embedding(strategy.strategy_text)

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO strategies VALUES (?,?,?,?,?,?,?,?,?,?)''',
                     (sid, json.dumps(skill_ids), strategy.context, strategy.strategy_text,
                      language, 1, 0, 1.0, now, now))
            c.execute('''INSERT OR REPLACE INTO strategy_embeddings VALUES (?,?,?)''',
                     (sid, json.dumps(emb), self._hash(strategy.strategy_text)))
            conn.commit()
            conn.close()
            return strategy
        except Exception as e:
            print(f"[StrategyMemory] Extraction failed: {e}")
            return None

    def retrieve_strategies(self, skill_ids: List[str], problem_text: str,
                            language: str = "python", top_k: int = 3) -> List[Strategy]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM strategies WHERE language IN (?, 'language_agnostic')", (language,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return []

        prob_emb = self._simple_embedding(problem_text)
        scored = []

        for row in rows:
            sid = row[0]
            stored_skills = json.loads(row[1])
            overlap = len(set(stored_skills) & set(skill_ids))
            skill_score = overlap / max(len(stored_skills), len(skill_ids), 1)

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT embedding FROM strategy_embeddings WHERE strategy_id = ?", (sid,))
            emb_row = c.fetchone()
            conn.close()

            emb_score = 0.0
            if emb_row and emb_row[0]:
                emb = json.loads(emb_row[0])
                emb_score = self._cosine_sim(prob_emb, emb)

            total = row[5] + row[6]
            success_rate = row[5] / max(total, 1)
            scored.append((skill_score * 0.5 + emb_score * 0.3 + success_rate * 0.2, sid, row))

        scored.sort(reverse=True)

        strategies = []
        for score, sid, row in scored[:top_k]:
            strategies.append(Strategy(
                id=row[0], skill_ids=json.loads(row[1]), context=row[2],
                strategy_text=row[3], language=row[4], success_count=row[5],
                failure_count=row[6], avg_code_complexity=row[7],
                created_at=row[8], last_used=row[9]
            ))
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE strategies SET last_used = ? WHERE id = ?",
                     (datetime.now().isoformat(), sid))
            conn.commit()
            conn.close()

        return strategies

    def record_outcome(self, strategy_id: str, success: bool):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        col = "success_count" if success else "failure_count"
        c.execute(f"UPDATE strategies SET {col} = {col} + 1 WHERE id = ?", (strategy_id,))
        conn.commit()
        conn.close()
