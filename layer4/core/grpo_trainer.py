"""grpo_trainer.py — GRPO training scaffold for self-improving code AI.

Layer 4 — v0.2.0.  Implements Group Relative Policy Optimization for code.
Based on ReflexiCoder (2603.05863) and TRL GRPOTrainer.

This is a SCAFFOLD — full training requires GPU and the TRL library.
Install: pip install trl transformers datasets
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class GRPORewardConfig:
    """Configuration for GRPO reward computation."""
    format_weight: float = 1.0      # Binary: correct format?
    correctness_weight: float = 2.0  # Binary: tests pass?
    efficiency_weight: float = 0.5   # Runtime vs reference
    readability_weight: float = 0.3  # Static analysis score
    cycle_penalty_weight: float = 0.1  # Penalize too many reflection cycles
    max_cycles: int = 5


@dataclass
class GRPOSample:
    """A single training sample with reflection trajectory."""
    prompt: str
    problem: str
    test_code: str
    language: str
    # Reflection trajectory: list of (reflection_text, code_attempt, test_result)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    final_code: str = ""
    final_passed: bool = False
    final_runtime_ms: float = 0.0


@dataclass
class GRPOTrainerScaffold:
    """Scaffold for GRPO training on code generation.

    Usage:
        1. Collect samples with reflection trajectories
        2. Define reward function using sandbox
        3. Run GRPO training with TRL
    """

    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    reward_config: GRPORewardConfig = field(default_factory=GRPORewardConfig)
    sandbox: Any = None
    llm_client: Any = None

    # Training hyperparameters (from ReflexiCoder)
    learning_rate: float = 1e-6
    num_generations: int = 8  # Group size G
    max_completion_length: int = 2048
    per_device_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    num_train_epochs: int = 2

    _samples: list[GRPOSample] = field(default_factory=list)

    def collect_sample(
        self,
        problem: str,
        test_code: str,
        language: str = "python",
        max_attempts: int = 5,
    ) -> GRPOSample:
        """Collect a training sample with reflection trajectory.

        Generates code, tests it, reflects on failure, retries.
        Each attempt becomes part of the trajectory.
        """
        sample = GRPOSample(
            prompt=self._build_prompt(problem, language),
            problem=problem,
            test_code=test_code,
            language=language,
        )

        context = ""
        for attempt in range(max_attempts):
            # Generate code with reflection context
            code = self._generate_code(sample.prompt, context, language)

            # Test in sandbox
            result = self._test_code(code, test_code, language)

            # Record trajectory step
            step = {
                "attempt": attempt,
                "code": code,
                "passed": result.get("success", False),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "runtime_ms": result.get("actual_runtime_ms", 0),
            }

            if result.get("success", False):
                sample.trajectory.append(step)
                sample.final_code = code
                sample.final_passed = True
                sample.final_runtime_ms = result.get("actual_runtime_ms", 0)
                break

            # Generate reflection
            reflection = self._generate_reflection(code, result)
            step["reflection"] = reflection
            sample.trajectory.append(step)
            context = reflection

        self._samples.append(sample)
        return sample

    def _build_prompt(self, problem: str, language: str) -> str:
        return f"""Solve the following programming problem in {language}.

Problem:
{problem}

Generate clean, correct, efficient code. Wrap your solution in ```{language} ... ```.
"""

    def _generate_code(self, prompt: str, reflection: str, language: str) -> str:
        """Generate code using LLM."""
        if not self.llm_client:
            return f"# TODO: implement\ndef solve():\n    pass"

        full_prompt = prompt
        if reflection:
            full_prompt += f"\n\nPrevious attempt failed. Reflection:\n{reflection}\n\nPlease fix the code."

        response = self.llm_client.complete(
            prompt=full_prompt,
            system_prompt=f"You are an expert {language} programmer.",
            max_tokens=1500,
            temperature=0.2,
        )
        if response.is_ok():
            text = response.value.content if hasattr(response.value, "content") else str(response.value)
            return self._extract_code(text, language)
        return ""

    def _extract_code(self, text: str, language: str) -> str:
        """Extract code from markdown blocks."""
        import re
        pattern = rf"```{language}\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: return whole text if no markdown
        return text.strip()

    def _test_code(self, code: str, test_code: str, language: str) -> dict[str, Any]:
        """Test code in sandbox."""
        if not self.sandbox:
            return {"success": False, "stderr": "No sandbox configured"}
        return self.sandbox.execute(code=code, test_code=test_code, language=language)

    def _generate_reflection(self, code: str, result: dict[str, Any]) -> str:
        """Generate reflection on failed code."""
        if not self.llm_client:
            return "Fix the errors."

        prompt = f"""The following code failed tests. Analyze why and suggest fixes.

Code:
```{code}```

Error:
{result.get('stderr', 'Unknown error')}

Provide a brief reflection (2-3 sentences) on what went wrong and how to fix it.
"""
        response = self.llm_client.complete(
            prompt=prompt,
            system_prompt="You are a debugging expert. Be concise.",
            max_tokens=200,
            temperature=0.1,
        )
        if response.is_ok():
            text = response.value.content if hasattr(response.value, "content") else str(response.value)
            return text.strip()
        return ""

    def compute_reward(self, sample: GRPOSample) -> float:
        """Compute GRPO reward for a sample.

        Based on ReflexiCoder's composite reward:
        R = format_gate * (correctness + efficiency + readability - cycle_penalty)
        """
        cfg = self.reward_config

        # Format gate: binary — did final code exist and have correct structure?
        format_ok = 1.0 if sample.final_code and len(sample.final_code) > 20 else 0.0

        # Correctness: binary pass/fail
        correctness = 1.0 if sample.final_passed else 0.0

        # Efficiency: inverse of runtime (normalized)
        efficiency = 0.0
        if sample.final_passed and sample.final_runtime_ms > 0:
            efficiency = max(0.0, 1.0 - sample.final_runtime_ms / 10000)

        # Readability: heuristic based on code structure
        readability = self._score_readability(sample.final_code)

        # Cycle penalty: penalize many attempts
        num_cycles = len(sample.trajectory)
        cycle_penalty = cfg.cycle_penalty_weight * max(0, num_cycles - 1)

        reward = format_ok * (
            cfg.correctness_weight * correctness
            + cfg.efficiency_weight * efficiency
            + cfg.readability_weight * readability
            - cycle_penalty
        )
        return reward

    def _score_readability(self, code: str) -> float:
        """Heuristic readability score."""
        if not code:
            return 0.0
        lines = code.split("\n")
        score = 0.5
        # Docstrings
        if '"""' in code or "'''" in code:
            score += 0.2
        # Comments
        comment_ratio = sum(1 for l in lines if l.strip().startswith("#")) / max(len(lines), 1)
        if 0.05 <= comment_ratio <= 0.3:
            score += 0.15
        # Line length
        avg_len = sum(len(l) for l in lines) / max(len(lines), 1)
        if avg_len < 80:
            score += 0.1
        # Function length
        func_lines = 0
        in_func = False
        for l in lines:
            if l.strip().startswith("def "):
                in_func = True
                func_start = 0
            if in_func:
                func_lines += 1
        if func_lines < 50:
            score += 0.05
        return min(1.0, score)

    def export_dataset(self, path: str) -> None:
        """Export samples to JSONL for TRL training."""
        import json
        with open(path, "w") as f:
            for sample in self._samples:
                # Build messages format for TRL
                messages = [{"role": "user", "content": sample.prompt}]
                for step in sample.trajectory:
                    if "reflection" in step:
                        messages.append({"role": "assistant", "content": step["code"]})
                        messages.append({"role": "user", "content": f"Tests failed. {step['reflection']}"})
                    else:
                        messages.append({"role": "assistant", "content": step["code"]})

                reward = self.compute_reward(sample)
                record = {
                    "prompt": messages,
                    "reward": reward,
                    "problem": sample.problem,
                    "language": sample.language,
                    "final_code": sample.final_code,
                    "passed": sample.final_passed,
                }
                f.write(json.dumps(record) + "\n")

    def train(self, dataset_path: Optional[str] = None) -> None:
        """Run GRPO training with TRL.

        This requires GPU and the trl library.
        """
        try:
            from trl import GRPOTrainer, GRPOConfig
            from transformers import AutoTokenizer, AutoModelForCausalLM
            from datasets import load_dataset
        except ImportError:
            print("TRL not installed. Run: pip install trl transformers datasets")
            return

        print("GRPO training scaffold — implement with your dataset")
        print(f"Model: {self.model_name}")
        print(f"Samples collected: {len(self._samples)}")
        print("See export_dataset() to save samples, then use TRL's GRPOTrainer")
