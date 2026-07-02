"""
Skill Ontology System
Maps coding problems to hierarchical skills and tracks mastery over time.
"""
import sqlite3
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime


@dataclass
class Skill:
    id: str
    name: str
    description: str
    category: str          # syntax, algorithm, pattern, architecture, domain
    parent_ids: List[str]
    language: str          # 'python', 'javascript', 'language_agnostic'
    mastery: float
    stability: float
    attempt_count: int
    success_count: int
    created_at: str
    last_updated: str


class SkillOntology:
    def __init__(self, db_path: str = "layer0/data/meta_learning/skills.db", llm_client=None):
        self.db_path = db_path
        self.llm = llm_client
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        self._seed_basic_skills()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            category TEXT,
            parent_ids TEXT,
            language TEXT,
            mastery REAL,
            stability REAL,
            attempt_count INTEGER,
            success_count INTEGER,
            created_at TEXT,
            last_updated TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS problem_skills (
            problem_id TEXT,
            skill_id TEXT,
            confidence REAL,
            extracted_at TEXT,
            PRIMARY KEY (problem_id, skill_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS mastery_history (
            skill_id TEXT,
            timestamp TEXT,
            mastery REAL,
            context TEXT
        )''')
        conn.commit()
        conn.close()

    def _seed_basic_skills(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM skills")
        if c.fetchone()[0] == 0:
            basics = [
                ("py_var", "Variable Assignment", "Declaring and assigning variables", "syntax", "", "python", 0.0),
                ("py_loop", "Loops", "For and while loops", "syntax", "", "python", 0.0),
                ("py_cond", "Conditionals", "If/else statements", "syntax", "", "python", 0.0),
                ("py_func", "Functions", "Defining and calling functions", "syntax", "py_var,py_loop,py_cond", "python", 0.0),
                ("py_rec", "Recursion", "Self-referential function calls", "algorithm", "py_func", "python", 0.0),
                ("py_io", "File I/O", "Reading and writing files", "syntax", "", "python", 0.0),
                ("py_err", "Error Handling", "Try/except blocks", "syntax", "py_cond", "python", 0.0),
                ("py_list", "List Operations", "Comprehensions, slicing, manipulation", "syntax", "", "python", 0.0),
                ("py_dict", "Dictionary Operations", "Key-value data structures", "syntax", "", "python", 0.0),
                ("py_re", "Regular Expressions", "Pattern matching in strings", "syntax", "", "python", 0.0),
                ("py_class", "Classes & OOP", "Object-oriented programming basics", "pattern", "py_func", "python", 0.0),
                ("py_async", "Async/Await", "Asynchronous programming patterns", "pattern", "py_func,py_err", "python", 0.0),
                ("py_dsa_arr", "Array Algorithms", "Searching, sorting, two-pointer", "algorithm", "py_loop,py_list", "python", 0.0),
                ("py_dsa_tree", "Tree Algorithms", "DFS, BFS on trees", "algorithm", "py_rec,py_dsa_arr", "python", 0.0),
                ("py_dsa_graph", "Graph Algorithms", "Graph traversal and pathfinding", "algorithm", "py_dsa_tree", "python", 0.0),
                ("py_dp", "Dynamic Programming", "Memoization and tabulation", "algorithm", "py_rec,py_dsa_arr", "python", 0.0),
                ("py_api", "API Integration", "HTTP requests and JSON parsing", "domain", "py_dict,py_err", "python", 0.0),
                ("py_debug", "Debugging Strategy", "Systematic bug isolation", "pattern", "py_err", "language_agnostic", 0.0),
            ]
            now = datetime.now().isoformat()
            for row in basics:
                parents = row[4] if row[4] else ""
                c.execute('''INSERT INTO skills VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (row[0], row[1], row[2], row[3], parents, row[5], row[6], 0.1, 0, 0, now, now))
            conn.commit()
        conn.close()

    def decompose_problem(self, problem_text: str, solution_code: str, problem_id: str) -> List[Tuple[str, float]]:
        """
        Identify skills required. Uses heuristics first, LLM fallback.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, name, description, category FROM skills")
        all_skills = c.fetchall()
        conn.close()

        matched = []
        text = (problem_text + " " + solution_code).lower()

        for sid, name, desc, cat in all_skills:
            score = 0.0
            keywords = [name.lower()] + desc.lower().split()
            for kw in keywords:
                if len(kw) > 3 and kw in text:
                    score += 0.3
            if score > 0.3:
                matched.append((sid, min(score, 1.0)))

        if self.llm and len(matched) < 2:
            matched = self._llm_decompose(problem_text, solution_code, all_skills)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now().isoformat()
        for sid, conf in matched:
            c.execute('''INSERT OR REPLACE INTO problem_skills VALUES (?,?,?,?)''',
                     (problem_id, sid, conf, now))
        conn.commit()
        conn.close()
        return matched

    def _llm_decompose(self, problem_text, solution_code, all_skills) -> List[Tuple[str, float]]:
        skills_text = "\n".join([f"- {s[0]}: {s[1]} ({s[3]})" for s in all_skills[:40]])
        prompt = f"""Given this coding problem and solution, identify which skills are demonstrated.
Return ONLY a JSON object like {{"skill_id": confidence, ...}}.

Skills:
{skills_text}

Problem: {problem_text[:500]}
Solution: {solution_code[:500]}"""
        try:
            response = self.llm.complete(prompt, system="You are a precise skill classifier.", temperature=0.1)
            result = json.loads(response.strip())
            return [(k, float(v)) for k, v in result.items() if isinstance(v, (int, float))]
        except Exception:
            return []

    def update_mastery(self, skill_id: str, success: bool, problem_complexity: float = 1.0):
        """
        Adaptive EMA update. Learns faster when stability is low.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT mastery, stability, attempt_count, success_count FROM skills WHERE id = ?", (skill_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return

        mastery, stability, attempts, successes = row
        attempts += 1
        if success:
            successes += 1

        alpha = 0.3 * (1 - stability) + 0.05 * stability
        alpha *= min(problem_complexity, 2.0)

        new_mastery = mastery + alpha * ((1.0 if success else 0.0) - mastery)
        new_mastery = max(0.0, min(1.0, new_mastery))
        new_stability = min(0.95, stability + 0.05)

        now = datetime.now().isoformat()
        c.execute('''UPDATE skills SET mastery=?, stability=?, attempt_count=?, success_count=?, last_updated=?
                     WHERE id=?''',
                 (new_mastery, new_stability, attempts, successes, now, skill_id))
        c.execute('''INSERT INTO mastery_history VALUES (?,?,?,?)''', (skill_id, now, new_mastery, "practice"))
        conn.commit()
        conn.close()

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return Skill(
                id=row[0], name=row[1], description=row[2], category=row[3],
                parent_ids=row[4].split(",") if row[4] else [],
                language=row[5], mastery=row[6], stability=row[7],
                attempt_count=row[8], success_count=row[9],
                created_at=row[10], last_updated=row[11]
            )
        return None

    def get_learning_edge(self, language: str = "python", limit: int = 5) -> List[Skill]:
        """
        Zone of Proximal Development: skills between 0.3 and 0.7 mastery.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""SELECT * FROM skills
                     WHERE language IN (?, 'language_agnostic')
                     AND mastery BETWEEN 0.3 AND 0.7
                     ORDER BY mastery ASC""", (language,))
        rows = c.fetchall()
        conn.close()
        skills = []
        for row in rows:
            skills.append(Skill(
                id=row[0], name=row[1], description=row[2], category=row[3],
                parent_ids=row[4].split(",") if row[4] else [],
                language=row[5], mastery=row[6], stability=row[7],
                attempt_count=row[8], success_count=row[9],
                created_at=row[10], last_updated=row[11]
            ))
        return skills[:limit]

    def get_skill_gaps(self, problem_id: str) -> Tuple[List[Skill], List[Skill]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT skill_id, confidence FROM problem_skills WHERE problem_id = ?", (problem_id,))
        req_skills = c.fetchall()
        conn.close()

        known, missing = [], []
        for sid, conf in req_skills:
            skill = self.get_skill(sid)
            if not skill:
                continue
            if skill.mastery >= 0.5 and skill.stability >= 0.3:
                known.append(skill)
            else:
                missing.append(skill)
        return known, missing

    def get_skill_path(self, target_skill_id: str) -> List[str]:
        path = []
        visited = set()
        queue = [target_skill_id]
        while queue:
            current = queue.pop(0)
            if current in visited or not current:
                continue
            visited.add(current)
            path.append(current)
            skill = self.get_skill(current)
            if skill:
                queue.extend(skill.parent_ids)
        return list(reversed(path))

    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), AVG(mastery), AVG(stability) FROM skills")
        total, avg_m, avg_s = c.fetchone()
        c.execute("SELECT COUNT(*) FROM skills WHERE mastery >= 0.8")
        mastered = c.fetchone()[0]
        conn.close()
        return {
            "total_skills": total,
            "average_mastery": round(avg_m or 0, 3),
            "average_stability": round(avg_s or 0, 3),
            "mastered_skills": mastered
        }
