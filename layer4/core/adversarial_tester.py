"""adversarial_tester.py — Adversarial test case generator.

Layer 4 — v0.2.0.  Based on Code-A1's adversarial co-evolution.
Generates tests designed to expose defects in candidate code.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class AdversarialTest:
    """A generated adversarial test case."""
    test_id: str
    input_data: str
    expected_output: str
    difficulty: str  # basic | edge | stress | adversarial
    generation_strategy: str
    target_weakness: str


@dataclass
class AdversarialTester:
    """Generates adversarial test cases to challenge candidate code.

    Inspired by Code-A1: separate test generation that actively
    tries to find bugs in the candidate's solution.
    """

    llm_client: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    def generate_tests(
        self,
        problem_description: str,
        candidate_code: str,
        existing_tests: list[dict[str, Any]],
        num_tests: int = 3,
    ) -> list[AdversarialTest]:
        """Generate adversarial tests targeting candidate weaknesses."""
        tests = []

        # Heuristic tests (fast, no LLM cost)
        tests.extend(self._generate_edge_cases(problem_description, candidate_code))
        tests.extend(self._generate_stress_tests(problem_description, candidate_code))

        # LLM-based adversarial tests
        if self.llm_client and not self.config.get("economy_mode", False):
            llm_tests = self._generate_llm_adversarial(problem_description, candidate_code, existing_tests, num_tests)
            tests.extend(llm_tests)

        return tests[:num_tests]

    def _generate_edge_cases(self, problem: str, code: str) -> list[AdversarialTest]:
        """Generate edge case tests heuristically."""
        tests = []
        # Common edge cases for algorithmic problems
        edge_inputs = [
            ("empty_input", "", ""),
            ("single_element", "[1]", ""),
            ("all_same", "[5,5,5,5]", ""),
            ("negative_numbers", "[-1,-2,-3]", ""),
            ("zero_values", "[0,0,0]", ""),
            ("max_int", "[2147483647]", ""),
            ("min_int", "[-2147483648]", ""),
            ("large_n", "[1]*100000", ""),
        ]
        for name, inp, exp in edge_inputs:
            tests.append(AdversarialTest(
                test_id=f"edge_{name}_{random.randint(1000,9999)}",
                input_data=inp,
                expected_output=exp,
                difficulty="edge",
                generation_strategy="heuristic_edge",
                target_weakness="boundary_handling",
            ))
        return tests

    def _generate_stress_tests(self, problem: str, code: str) -> list[AdversarialTest]:
        """Generate stress tests for performance validation."""
        tests = []
        # Performance stress inputs
        stress_inputs = [
            ("large_random", "[random.randint(1,1000) for _ in range(10000)]", ""),
            ("sorted_reverse", "list(range(10000,0,-1))", ""),
            ("already_sorted", "list(range(10000))", ""),
        ]
        for name, inp, exp in stress_inputs:
            tests.append(AdversarialTest(
                test_id=f"stress_{name}_{random.randint(1000,9999)}",
                input_data=inp,
                expected_output=exp,
                difficulty="stress",
                generation_strategy="heuristic_stress",
                target_weakness="performance",
            ))
        return tests

    def _generate_llm_adversarial(
        self,
        problem: str,
        code: str,
        existing_tests: list[dict[str, Any]],
        num_tests: int,
    ) -> list[AdversarialTest]:
        """Use LLM to generate targeted adversarial tests."""
        tests = []
        if not self.llm_client:
            return tests

        try:
            existing = "\n".join([f"- {t.get('input','')}" for t in existing_tests[:5]])
            prompt = f"""Given this problem and solution, generate adversarial test cases that would break the solution.

Problem:
{problem}

Solution:
```{code}```

Existing tests:
{existing}

Generate {num_tests} test cases that target potential weaknesses. For each:
1. Input that might break the solution
2. Expected output
3. What weakness it targets

Format:
TEST 1
Input: <input>
Expected: <output>
Target: <weakness>
"""
            response = self.llm_client.complete(
                prompt=prompt,
                system_prompt="You are an expert at finding bugs in code. Generate evil test cases.",
                max_tokens=800,
                temperature=0.7,
            )
            if response.is_ok():
                text = response.value.content if hasattr(response.value, "content") else str(response.value)
                # Parse test cases
                current = {}
                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("TEST"):
                        if current and "input" in current:
                            tests.append(AdversarialTest(
                                test_id=f"adv_{random.randint(1000,9999)}",
                                input_data=current.get("input", ""),
                                expected_output=current.get("expected", ""),
                                difficulty="adversarial",
                                generation_strategy="llm_adversarial",
                                target_weakness=current.get("target", "unknown"),
                            ))
                        current = {}
                    elif line.startswith("Input:"):
                        current["input"] = line.replace("Input:", "").strip()
                    elif line.startswith("Expected:"):
                        current["expected"] = line.replace("Expected:", "").strip()
                    elif line.startswith("Target:"):
                        current["target"] = line.replace("Target:", "").strip()
                if current and "input" in current:
                    tests.append(AdversarialTest(
                        test_id=f"adv_{random.randint(1000,9999)}",
                        input_data=current.get("input", ""),
                        expected_output=current.get("expected", ""),
                        difficulty="adversarial",
                        generation_strategy="llm_adversarial",
                        target_weakness=current.get("target", "unknown"),
                    ))
        except Exception:
            pass
        return tests

    def evaluate_with_adversarial(
        self,
        code: str,
        adversarial_tests: list[AdversarialTest],
        sandbox: Any,
    ) -> dict[str, Any]:
        """Run candidate against adversarial tests."""
        passed = 0
        failed_tests = []
        for test in adversarial_tests:
            test_code = f"""
input_data = {test.input_data}
expected = {test.expected_output}
result = solve(input_data)
assert result == expected, f"Failed: {{result}} != {{expected}}"
"""
            result = sandbox.execute(code=code, test_code=test_code, language="python")
            if result.get("success", False):
                passed += 1
            else:
                failed_tests.append({
                    "test_id": test.test_id,
                    "input": test.input_data,
                    "target": test.target_weakness,
                    "error": result.get("stderr", "")[:200],
                })
        return {
            "total_tests": len(adversarial_tests),
            "passed": passed,
            "failed": len(failed_tests),
            "pass_rate": passed / max(len(adversarial_tests), 1),
            "failed_tests": failed_tests,
        }
