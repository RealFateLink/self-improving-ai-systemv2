"""
Meta-Learning Orchestrator
Integrates skill ontology, strategy memory, repair memory, and analogies
into the generation and learning loop.
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

try:
    from .skill_ontology import SkillOntology
    from .strategy_memory import StrategyMemory
    from .repair_strategy_memory import RepairStrategyMemory
    from .cross_domain_analogizer import CrossDomainAnalogizer
except ImportError:
    from skill_ontology import SkillOntology
    from strategy_memory import StrategyMemory
    from repair_strategy_memory import RepairStrategyMemory
    from cross_domain_analogizer import CrossDomainAnalogizer


class _LLMAdapter:
    """
    Adapts the full LLMClient to the simple complete(prompt, system, temperature) -> str
    interface expected by the meta-learning components.
    """
    def __init__(self, client):
        self._client = client

    def complete(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        return self._client.complete_text(prompt, system=system, temperature=temperature)


class MetaLearningOrchestrator:
    def __init__(
        self,
        llm_client,
        config: Optional[Dict] = None,
        base_db_dir: str = "layer0/data/meta_learning",
    ):
        self.config = config or {}

        # Wrap if it's the full LLMClient (has complete_text); pass through if already adapted.
        if hasattr(llm_client, "complete_text"):
            self.llm = _LLMAdapter(llm_client)
        else:
            self.llm = llm_client

        os.makedirs(base_db_dir, exist_ok=True)

        self.skills = SkillOntology(
            db_path=os.path.join(base_db_dir, "skills.db"), llm_client=self.llm
        )
        self.strategies = StrategyMemory(
            db_path=os.path.join(base_db_dir, "strategies.db"), llm_client=self.llm
        )
        self.repairs = RepairStrategyMemory(
            db_path=os.path.join(base_db_dir, "repairs.db"), llm_client=self.llm
        )
        self.analogies = CrossDomainAnalogizer(
            db_path=os.path.join(base_db_dir, "analogies.db"), llm_client=self.llm
        )

        self._traces_db = os.path.join(base_db_dir, "traces.db")
        self._init_trace_db()

    # ------------------------------------------------------------------ #
    # Reasoning trace store                                                #
    # ------------------------------------------------------------------ #

    def _init_trace_db(self):
        conn = sqlite3.connect(self._traces_db)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS reasoning_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id TEXT,
            language TEXT,
            system_prompt_hash TEXT,
            reasoning TEXT,
            code TEXT,
            tests_passed BOOLEAN,
            created_at TEXT
        )''')
        conn.commit()
        conn.close()

    def store_reasoning_trace(
        self,
        problem_id: str,
        language: str,
        system_prompt: str,
        reasoning: str,
        code: str,
        tests_passed: bool,
    ) -> None:
        sys_hash = hashlib.md5(system_prompt.encode()).hexdigest()[:12]
        conn = sqlite3.connect(self._traces_db)
        c = conn.cursor()
        c.execute(
            '''INSERT INTO reasoning_traces
               (problem_id, language, system_prompt_hash, reasoning, code, tests_passed, created_at)
               VALUES (?,?,?,?,?,?,?)''',
            (problem_id, language, sys_hash, reasoning, code, tests_passed, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_trace_stats(self) -> Dict:
        conn = sqlite3.connect(self._traces_db)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(tests_passed) FROM reasoning_traces")
        total, passed = c.fetchone()
        conn.close()
        return {
            "total_traces": total or 0,
            "passing_traces": int(passed or 0),
        }

    # ------------------------------------------------------------------ #
    # Core loop methods (synchronous — no actual I/O needs await)          #
    # ------------------------------------------------------------------ #

    def process_learning_episode(
        self,
        episode: Dict,
        reasoning: str = "",
    ) -> Dict:
        """
        episode = {
            "problem_id": str,
            "problem_text": str,
            "language": str,
            "code_before": Optional[str],   # set if this was a repair attempt
            "code_after": str,
            "error_message": Optional[str],
            "tests_passed": bool,
        }
        reasoning: the model's reasoning trace (if captured), stored for future fine-tuning.
        """
        problem_id = episode["problem_id"]
        problem_text = episode["problem_text"]
        language = episode.get("language", "python")
        code = episode["code_after"]
        success = episode.get("tests_passed", False)
        error = episode.get("error_message") or ""
        previous_code = episode.get("code_before")

        # 1. Identify skills
        skill_matches = self.skills.decompose_problem(problem_text, code, problem_id)
        skill_ids = [sid for sid, _ in skill_matches]

        # 2. Update mastery for each matched skill
        for sid, conf in skill_matches:
            self.skills.update_mastery(sid, success, problem_complexity=conf)

        # 3. Extract strategy on success
        if success:
            self.strategies.extract_strategy(problem_text, code, skill_ids, language)

        # 4. Extract repair pattern when we turned a failure into a success
        if previous_code and success and error:
            self.repairs.extract_repair(previous_code, code, error, skill_ids, language)

        # 5. Store reasoning trace
        if reasoning or code:
            self.store_reasoning_trace(
                problem_id=problem_id,
                language=language,
                system_prompt="",   # caller can pass hash via build_meta_prompt result
                reasoning=reasoning,
                code=code,
                tests_passed=success,
            )

        return {
            "skill_ids": skill_ids,
            "mastery_updates": {
                sid: self.skills.get_skill(sid).mastery
                for sid in skill_ids
                if self.skills.get_skill(sid)
            },
            "new_strategy": success,
            "new_repair": bool(previous_code and success and error),
            "learning_edge": [s.id for s in self.skills.get_learning_edge(language)],
        }

    def build_meta_prompt(
        self,
        problem_text: str,
        language: str = "python",
        target_problem_id: Optional[str] = None,
    ) -> Dict:
        """
        Builds a skill-conditioned system prompt with retrieved strategies and warnings.
        Returns a dict with system_prompt, user_prompt, skill_details, etc.
        """
        # Identify required skills
        if target_problem_id:
            conn = sqlite3.connect(self.skills.db_path)
            c = conn.cursor()
            c.execute(
                "SELECT skill_id, confidence FROM problem_skills WHERE problem_id = ?",
                (target_problem_id,),
            )
            rows = c.fetchall()
            conn.close()
            required_skills = rows if rows else self.skills.decompose_problem(
                problem_text, "", target_problem_id
            )
        else:
            temp_id = f"temp_{abs(hash(problem_text)) % 10**8}"
            required_skills = self.skills.decompose_problem(problem_text, "", temp_id)

        skill_ids = [sid for sid, _ in required_skills]

        # Build skill detail list with mastery status
        skill_details = []
        for sid, conf in required_skills:
            s = self.skills.get_skill(sid)
            if not s:
                continue
            status = (
                "mastered" if s.mastery >= 0.8
                else "learning" if s.mastery >= 0.3
                else "unknown"
            )
            skill_details.append({
                "id": sid,
                "name": s.name,
                "mastery": round(s.mastery, 2),
                "stability": round(s.stability, 2),
                "status": status,
            })

        # Retrieve past winning strategies
        strategies = self.strategies.retrieve_strategies(skill_ids, problem_text, language, top_k=3)

        # Cross-domain analogies for non-Python targets
        analogy_primers = []
        if language != "python":
            mastered_ids = [s["id"] for s in skill_details if s["status"] == "mastered"]
            analogy_primers = self.analogies.get_transfer_primers(mastered_ids, "python", language)

        # Assemble system prompt
        sections = ["You are an expert software engineer who learns from every problem."]

        sections.append("\n## Skills Required for This Problem")
        for sd in skill_details:
            tag = "CONFIDENTLY USE" if sd["status"] == "mastered" else "FOCUS HERE — PRACTICE THIS"
            sections.append(f"- {sd['name']} (mastery {sd['mastery']}) → {tag}")

        if strategies:
            sections.append("\n## Proven Strategies from Past Successes")
            for i, st in enumerate(strategies, 1):
                sections.append(f"{i}. [{st.context}] {st.strategy_text}")

        weak = [s for s in skill_details if s["status"] != "mastered"]
        if weak:
            sections.append("\n## Caution Zone")
            sections.append(
                "Pay special attention to edge cases and error handling in skills marked FOCUS HERE."
            )

        if analogy_primers:
            sections.append(f"\n## Transfer from Python to {language}")
            for ap in analogy_primers[:2]:
                sections.append(f"- {ap['concept']}: {ap['pitfalls']}")

        system_prompt = "\n".join(sections)

        user_prompt = (
            f"Solve the following problem in {language}.\n\n"
            f"{problem_text}\n\n"
            f"IMPORTANT: First, outline your approach in 2-4 sentences explaining which skills "
            f"you will use and how. Then write clean, efficient code.\n"
        )

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "skill_details": skill_details,
            "retrieved_strategies": len(strategies),
            "target_skills": [s["id"] for s in skill_details if s["status"] != "mastered"],
        }

    # ------------------------------------------------------------------ #
    # Curriculum                                                           #
    # ------------------------------------------------------------------ #

    def get_curriculum_recommendation(self, language: str = "python") -> Dict:
        """
        Replaces random/difficulty-based curriculum selection with skill-gap analysis.
        """
        edge_skills = self.skills.get_learning_edge(language, limit=5)
        stats = self.skills.get_stats()

        # Find prerequisite skills that are blocking edge skills
        blocking = []
        for s in edge_skills:
            path = self.skills.get_skill_path(s.id)
            for prereq_id in path[:-1]:
                p = self.skills.get_skill(prereq_id)
                if p and p.mastery < 0.5:
                    blocking.append(p)

        # Deduplicate
        seen: set = set()
        unique_blocking = []
        for b in blocking:
            if b.id not in seen:
                seen.add(b.id)
                unique_blocking.append(b)

        if unique_blocking:
            rec = "drill_prerequisites"
            focus = unique_blocking[:3]
        else:
            rec = "deliberate_practice"
            focus = edge_skills[:3]

        return {
            "recommendation": rec,
            "focus_skills": [{"id": s.id, "name": s.name, "mastery": s.mastery} for s in focus],
            "stats": stats,
        }

    def get_stats(self) -> Dict:
        return {
            "skills": self.skills.get_stats(),
            "traces": self.get_trace_stats(),
        }
