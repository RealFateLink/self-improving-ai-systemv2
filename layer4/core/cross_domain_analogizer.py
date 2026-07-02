"""
Cross-Domain Analogizer
Builds transferable knowledge across programming languages.
"""
import sqlite3
import json
import os
from typing import List, Dict, Optional
from datetime import datetime


class CrossDomainAnalogizer:
    def __init__(self, db_path: str = "layer0/data/meta_learning/analogies.db", llm_client=None):
        self.db_path = db_path
        self.llm = llm_client
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS analogies (
            id TEXT PRIMARY KEY,
            skill_id TEXT,
            concept_name TEXT,
            source_language TEXT,
            target_language TEXT,
            source_pattern TEXT,
            target_pattern TEXT,
            common_pitfalls TEXT,
            created_at TEXT
        )''')
        conn.commit()
        conn.close()

    def generate_analogy_card(self, skill_id: str, skill_name: str, skill_description: str,
                              source_language: str, target_language: str) -> Optional[Dict]:
        if not self.llm:
            return None

        prompt = f"""Create a learning transfer card: {source_language} → {target_language}.

Concept: {skill_name} — {skill_description}

Return JSON:
{{
  "concept_name": "...",
  "source_pattern": "code or pseudocode",
  "target_pattern": "code in {target_language}",
  "common_pitfalls": "text"
}}"""

        try:
            response = self.llm.complete(prompt, system="You are a polyglot programming educator.", temperature=0.3)
            result = json.loads(response.strip())

            aid = f"analogy_{source_language}_to_{target_language}_{skill_id}"
            now = datetime.now().isoformat()

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO analogies VALUES (?,?,?,?,?,?,?,?,?)''',
                     (aid, skill_id, result.get("concept_name", skill_name),
                      source_language, target_language,
                      result.get("source_pattern", ""),
                      result.get("target_pattern", ""),
                      result.get("common_pitfalls", ""),
                      now))
            conn.commit()
            conn.close()
            return result
        except Exception as e:
            print(f"[Analogizer] Generation failed: {e}")
            return None

    def get_transfer_primers(self, known_skill_ids: List[str],
                             source_language: str, target_language: str) -> List[Dict]:
        if not known_skill_ids:
            return []
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        placeholders = ','.join('?' * len(known_skill_ids))
        c.execute(f"""SELECT * FROM analogies
                      WHERE skill_id IN ({placeholders})
                      AND source_language = ? AND target_language = ?""",
                  (*known_skill_ids, source_language, target_language))
        rows = c.fetchall()
        conn.close()

        return [{
            "skill_id": r[1], "concept": r[2], "source": r[5],
            "target": r[6], "pitfalls": r[7]
        } for r in rows]

    def prepare_new_language(self, skill_ontology, source_language: str, target_language: str) -> List[Dict]:
        """
        Pre-generate analogy cards for all mastered skills before starting a new language.
        Call this once at language transition.
        """
        conn = sqlite3.connect(skill_ontology.db_path)
        c = conn.cursor()
        c.execute("SELECT id, name, description FROM skills WHERE mastery > 0.8 AND language = ?",
                  (source_language,))
        rows = c.fetchall()
        conn.close()

        cards = []
        for sid, name, desc in rows:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM analogies WHERE skill_id = ? AND target_language = ?",
                     (sid, target_language))
            if c.fetchone()[0] == 0:
                card = self.generate_analogy_card(sid, name, desc, source_language, target_language)
                if card:
                    cards.append(card)
            conn.close()
        return cards
