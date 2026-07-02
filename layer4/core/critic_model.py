"""critic_model.py — LLM-based code critic for structured feedback.

Layer 4 — v0.2.0.  Implements Critic-RL style critique generation.
Produces structured, actionable feedback on code candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class CriticIssue:
    """A single critique issue."""
    category: str  # correctness | efficiency | readability | safety | style
    severity: str  # critical | major | minor | info
    line_number: int | None
    description: str
    suggestion: str
    confidence: float  # 0.0–1.0


@dataclass(frozen=True)
class CriticResult:
    """Aggregate critique result."""
    candidate_id: str
    issues: tuple[CriticIssue, ...]
    overall_score: float  # 0.0–1.0
    summary: str
    actionable_feedback: str


@dataclass
class CriticModel:
    """LLM-based code critic producing structured feedback.

    Based on Critic-RL (HKUNLP) and Critique-Coder approaches.
    """

    llm_client: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    def critique(
        self,
        candidate: Any,
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Critique a code candidate."""
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            code = getattr(candidate, "code", "")
            cid = getattr(candidate, "candidate_id", "unknown")
            language = (
                candidate.metadata.get("language", "python")
                if hasattr(candidate, "metadata") else "python"
            )

            # Heuristic pre-check (fast, no LLM cost)
            issues = self._heuristic_critique(code, language)

            # LLM-based deep critique
            if self.llm_client and not cycle_context.get("economy_mode", False):
                llm_issues = self._llm_critique(code, language, task)
                issues.extend(llm_issues)

            # Score computation
            critical = sum(1 for i in issues if i.severity == "critical")
            major = sum(1 for i in issues if i.severity == "major")
            minor = sum(1 for i in issues if i.severity == "minor")

            score = max(0.0, 1.0 - critical * 0.3 - major * 0.15 - minor * 0.05)

            summary = self._generate_summary(issues, score)
            actionable = self._generate_actionable(issues)

            result = CriticResult(
                candidate_id=cid,
                issues=tuple(issues),
                overall_score=score,
                summary=summary,
                actionable_feedback=actionable,
            )

            return True, ModuleResult(primary=result)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Critique failed: {exc}",
                is_retryable=True,
            )

    def _heuristic_critique(self, code: str, language: str) -> list[CriticIssue]:
        """Fast heuristic critique (no LLM cost)."""
        issues = []
        lines = code.split("\n")

        if language == "python":
            # Check for bare except
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("except:"):
                    issues.append(CriticIssue(
                        category="safety", severity="major", line_number=i,
                        description="Bare 'except:' catches SystemExit and KeyboardInterrupt",
                        suggestion="Use 'except Exception:' or more specific exceptions",
                        confidence=0.95,
                    ))
                if "==" in stripped and "None" in stripped:
                    issues.append(CriticIssue(
                        category="correctness", severity="minor", line_number=i,
                        description="Using '== None' instead of 'is None'",
                        suggestion="Use 'is None' for identity comparison",
                        confidence=0.9,
                    ))

            # Check for mutable default args
            for i, line in enumerate(lines, 1):
                if "def " in line and "=[]" in line:
                    issues.append(CriticIssue(
                        category="correctness", severity="critical", line_number=i,
                        description="Mutable default argument (list) will be shared across calls",
                        suggestion="Use 'None' as default and initialize inside function",
                        confidence=0.95,
                    ))
                if "def " in line and "={}" in line:
                    issues.append(CriticIssue(
                        category="correctness", severity="critical", line_number=i,
                        description="Mutable default argument (dict) will be shared across calls",
                        suggestion="Use 'None' as default and initialize inside function",
                        confidence=0.95,
                    ))

            # Check for recursion without base case hint
            func_names = set()
            for line in lines:
                if line.strip().startswith("def "):
                    name = line.strip().split("(")[0].replace("def ", "").strip()
                    func_names.add(name)
            for i, line in enumerate(lines, 1):
                for name in func_names:
                    if f"{name}(" in line and not line.strip().startswith("def "):
                        # Simple heuristic: check if function has early return
                        issues.append(CriticIssue(
                            category="correctness", severity="info", line_number=i,
                            description=f"Recursive call to '{name}' — ensure base case exists",
                            suggestion="Verify termination condition is reachable",
                            confidence=0.6,
                        ))
                        break

        return issues

    def _llm_critique(self, code: str, language: str, task: Any) -> list[CriticIssue]:
        """Deep critique using LLM."""
        issues = []
        if not self.llm_client:
            return issues

        try:
            prompt = f"""You are an expert code reviewer. Review this {language} code for issues.

For each issue, provide:
- Category: correctness | efficiency | readability | safety | style
- Severity: critical | major | minor | info
- Line number (if applicable)
- Description
- Suggestion for fix

Code:
```{language}
{code[:3000]}
```

Format each issue as:
CATEGORY | SEVERITY | LINE | DESCRIPTION | SUGGESTION
"""
            response = self.llm_client.complete(
                prompt=prompt,
                system_prompt="You are a strict code reviewer. Be concise and actionable.",
                max_tokens=1000,
                temperature=0.1,
            )
            if response.is_ok():
                text = response.value.content if hasattr(response.value, "content") else str(response.value)
                for line in text.split("\n"):
                    line = line.strip()
                    if "|" in line and line[0].isalpha():
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 4:
                            issues.append(CriticIssue(
                                category=parts[0].lower(),
                                severity=parts[1].lower(),
                                line_number=int(parts[2]) if parts[2].isdigit() else None,
                                description=parts[3],
                                suggestion=parts[4] if len(parts) > 4 else "",
                                confidence=0.7,
                            ))
        except Exception:
            pass

        return issues

    def _generate_summary(self, issues: list[CriticIssue], score: float) -> str:
        if not issues:
            return "No issues found. Code looks good!"
        by_severity = {"critical": 0, "major": 0, "minor": 0, "info": 0}
        for i in issues:
            by_severity[i.severity] = by_severity.get(i.severity, 0) + 1
        return (
            f"Score: {score:.2f}. "
            f"Issues: {by_severity['critical']} critical, {by_severity['major']} major, "
            f"{by_severity['minor']} minor, {by_severity['info']} info."
        )

    def _generate_actionable(self, issues: list[CriticIssue]) -> str:
        critical = [i for i in issues if i.severity == "critical"]
        if critical:
            return f"Fix critical issue: {critical[0].description}. {critical[0].suggestion}"
        major = [i for i in issues if i.severity == "major"]
        if major:
            return f"Address: {major[0].description}. {major[0].suggestion}"
        return "Minor improvements possible. Review info-level suggestions."
