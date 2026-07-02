"""synthetic_data_generator.py — Generate training data using API models.

Layer 4 — v0.2.0.  Uses Claude/DeepSeek as TEACHER to generate
high-quality (problem, solution, test, reflection) tuples.

This is NOT learning — it's data generation. The learning happens
when a LOCAL model is trained on this data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class TrainingExample:
    """A single training example for code generation."""
    problem_id: str
    problem_description: str
    language: str
    solution_code: str
    test_code: str
    reflection: str  # How the model thought about solving it
    difficulty: str
    source: str  # "api_teacher" | "self_play" | "curated"
    execution_result: dict[str, Any]
    quality_score: float


@dataclass
class SyntheticDataGenerator:
    """Generates synthetic training data using API models.

    The API model acts as a TEACHER — it generates data but
    does NOT learn. Learning happens on a separate local model.
    """

    llm_client: Any = None  # API model (Claude/DeepSeek)
    sandbox: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    # Quality thresholds
    min_pass_rate: float = 1.0  # Must pass all tests
    max_attempts_per_problem: int = 5

    def generate_from_problem(
        self,
        problem: dict[str, Any],
        num_solutions: int = 3,
    ) -> list[TrainingExample]:
        """Generate verified training examples from a problem.

        Args:
            problem: Dict with 'description', 'test_code', 'language', 'problem_id'
            num_solutions: How many solutions to generate

        Returns:
            List of verified TrainingExamples that pass all tests
        """
        examples = []
        problem_id = problem.get("problem_id", "unknown")
        description = problem.get("description", "")
        test_code = problem.get("test_code", "")
        language = problem.get("language", "python")

        for attempt in range(self.max_attempts_per_problem):
            if len(examples) >= num_solutions:
                break

            # Generate solution with chain-of-thought
            solution_data = self._generate_solution(description, language, attempt)
            if not solution_data:
                continue

            code = solution_data["code"]
            reflection = solution_data["reflection"]

            # Verify with sandbox
            if self.sandbox:
                result = self.sandbox.execute(code=code, test_code=test_code, language=language)
                if not result.get("success", False):
                    # Try to fix based on error
                    fixed = self._attempt_fix(description, code, result.get("stderr", ""), language)
                    if fixed:
                        code = fixed["code"]
                        reflection += f"\nFix: {fixed['reflection']}"
                        result = self.sandbox.execute(code=code, test_code=test_code, language=language)

                if result.get("success", False):
                    examples.append(TrainingExample(
                        problem_id=problem_id,
                        problem_description=description,
                        language=language,
                        solution_code=code,
                        test_code=test_code,
                        reflection=reflection,
                        difficulty=problem.get("difficulty", "medium"),
                        source="api_teacher",
                        execution_result={
                            "success": True,
                            "runtime_ms": result.get("actual_runtime_ms", 0),
                        },
                        quality_score=self._compute_quality_score(code, result),
                    ))

        return examples

    def _generate_solution(self, description: str, language: str, attempt: int) -> Optional[dict[str, str]]:
        """Generate a solution with chain-of-thought reasoning."""
        if not self.llm_client:
            return None

        prompt = f"""Solve this {language} programming problem. Think step by step.

Problem:
{description}

Provide:
1. Your reasoning process (how you approach the problem)
2. The final solution code

Format your response as:
REASONING:
<your thinking>

CODE:
```{language}
<your solution>
```
"""

        # Vary temperature for diversity
        temp = 0.2 + attempt * 0.2

        response = self.llm_client.complete(
            prompt=prompt,
            system_prompt=f"You are an expert {language} programmer. Think carefully before coding.",
            temperature=temp,
            max_tokens=2000,
        )

        if not response.is_ok():
            return None

        text = response.value.content if hasattr(response.value, "content") else str(response.value)

        # Parse reasoning and code
        reasoning = ""
        code = ""

        if "REASONING:" in text and "CODE:" in text:
            parts = text.split("CODE:", 1)
            reasoning = parts[0].replace("REASONING:", "").strip()
            code_block = parts[1]
            # Extract code from markdown
            import re
            match = re.search(rf"```{language}\n(.*?)```", code_block, re.DOTALL)
            if match:
                code = match.group(1).strip()
            else:
                code = code_block.strip()
        else:
            # Fallback: just extract code
            import re
            match = re.search(rf"```{language}\n(.*?)```", text, re.DOTALL)
            if match:
                code = match.group(1).strip()
                reasoning = "Extracted from response"
            else:
                code = text.strip()
                reasoning = "No explicit reasoning provided"

        return {"code": code, "reflection": reasoning}

    def _attempt_fix(self, description: str, code: str, error: str, language: str) -> Optional[dict[str, str]]:
        """Attempt to fix a failing solution."""
        if not self.llm_client or not error:
            return None

        prompt = f"""This {language} code has an error. Fix it.

Problem:
{description}

Code:
```{language}
{code}
```

Error:
{error}

Provide the fixed code and a brief explanation of what was wrong.

FIXED CODE:
```{language}
<fixed code>
```

EXPLANATION:
<explanation>
"""

        response = self.llm_client.complete(
            prompt=prompt,
            system_prompt="You are a debugging expert.",
            temperature=0.1,
            max_tokens=1500,
        )

        if not response.is_ok():
            return None

        text = response.value.content if hasattr(response.value, "content") else str(response.value)

        import re
        match = re.search(rf"```{language}\n(.*?)```", text, re.DOTALL)
        if match:
            fixed_code = match.group(1).strip()
            explanation = text.split("EXPLANATION:")[-1].strip() if "EXPLANATION:" in text else "Fixed based on error"
            return {"code": fixed_code, "reflection": explanation}

        return None

    def _compute_quality_score(self, code: str, result: dict[str, Any]) -> float:
        """Compute quality score for filtering."""
        score = 0.5

        # Passes tests
        if result.get("success", False):
            score += 0.3

        # Runtime efficiency
        runtime = result.get("actual_runtime_ms", 1000)
        if runtime < 100:
            score += 0.1
        elif runtime < 500:
            score += 0.05

        # Code length (shorter is better, within reason)
        lines = len(code.split("\n"))
        if 10 < lines < 50:
            score += 0.05

        # Has docstring/comments
        if '"""' in code or "'''" in code:
            score += 0.05

        return min(1.0, score)

    def export_dataset(self, examples: list[TrainingExample], path: str) -> None:
        """Export examples to JSONL for training."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for ex in examples:
                record = {
                    "problem_id": ex.problem_id,
                    "problem": ex.problem_description,
                    "language": ex.language,
                    "solution": ex.solution_code,
                    "test": ex.test_code,
                    "reflection": ex.reflection,
                    "difficulty": ex.difficulty,
                    "quality_score": ex.quality_score,
                }
                f.write(json.dumps(record) + "\n")

    def generate_batch(
        self,
        problems: list[dict[str, Any]],
        output_path: str,
        target_examples: int = 1000,
    ) -> dict[str, Any]:
        """Generate a full training dataset from a list of problems.

        Returns stats about generation.
        """
        all_examples = []
        stats = {"problems_processed": 0, "examples_generated": 0, "failures": 0}

        for problem in problems:
            if len(all_examples) >= target_examples:
                break

            examples = self.generate_from_problem(problem, num_solutions=2)
            all_examples.extend(examples)

            stats["problems_processed"] += 1
            stats["examples_generated"] += len(examples)
            if not examples:
                stats["failures"] += 1

        # Export
        self.export_dataset(all_examples, output_path)

        stats["total_examples"] = len(all_examples)
        stats["avg_quality"] = sum(ex.quality_score for ex in all_examples) / max(len(all_examples), 1)
        stats["output_path"] = output_path

        return stats
