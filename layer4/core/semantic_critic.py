"""semantic_critic.py — LLM-based code review.

Stage 7.  Smell detection, pattern matching, maintainability/readability scoring.
SKIP in economy mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["SemanticCritic", "CritiqueResult"]


@dataclass(frozen=True)
class CritiqueIssue:
    """A semantic issue found during critique."""
    category: str     # smell | pattern_mismatch | readability | complexity
    severity: str     # minor | moderate | major
    description: str
    suggestion: str = ""
    confidence: float = 0.5


@dataclass(frozen=True)
class CritiqueResult:
    """Aggregate critique for a candidate."""
    candidate_id: str
    issues: tuple[CritiqueIssue, ...]
    maintainability_score: float  # 0.0–1.0
    readability_score: float      # 0.0–1.0
    overall_quality: float        # 0.0–1.0
    patterns_matched: list[str] = field(default_factory=list)
    smells_detected: list[str] = field(default_factory=list)


@dataclass
class SemanticCritic:
    """LLM-based semantic review of code quality.

    Dependencies:
      - llm_client (Layer 2): for LLM-based analysis
      - pattern_manager (Layer 3): for pattern matching
    """

    llm_client: Any = None
    pattern_manager: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    def critique(
        self,
        candidate: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Critique a single candidate.

        Returns (True, ModuleResult) or (False, ModuleError).
        Skipped entirely in economy mode (returns neutral result).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        # Economy mode → skip.
        if cycle_context.get("economy_mode", False):
            neutral = CritiqueResult(
                candidate_id=getattr(candidate, "candidate_id", "unknown"),
                issues=(),
                maintainability_score=0.5,
                readability_score=0.5,
                overall_quality=0.5,
            )
            return True, ModuleResult(primary=neutral)

        try:
            code = getattr(candidate, "code", "")
            cid = getattr(candidate, "candidate_id", "unknown")

            issues: list[CritiqueIssue] = []
            patterns_matched: list[str] = []
            smells: list[str] = []

            # LLM-based analysis.
            if self.llm_client:
                llm_issues = self._llm_review(code)
                issues.extend(llm_issues)

            # Heuristic smell detection.
            smell_issues = self._detect_smells(code)
            issues.extend(smell_issues)
            smells = [i.description for i in smell_issues]

            # Pattern matching.
            if self.pattern_manager:
                patterns_matched = self._check_patterns(code)

            # Score computation.
            major_count = sum(1 for i in issues if i.severity == "major")
            moderate_count = sum(1 for i in issues if i.severity == "moderate")

            maintainability = max(0.0, 1.0 - major_count * 0.2 - moderate_count * 0.05)
            readability = self._score_readability(code)
            overall = (maintainability * 0.5 + readability * 0.3 + 0.2 * (1.0 - len(issues) * 0.02))
            overall = max(0.0, min(1.0, overall))

            result = CritiqueResult(
                candidate_id=cid,
                issues=tuple(issues),
                maintainability_score=maintainability,
                readability_score=readability,
                overall_quality=overall,
                patterns_matched=patterns_matched,
                smells_detected=smells,
            )

            return True, ModuleResult(primary=result)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Semantic critique failed: {exc}",
                is_retryable=True,
            )

    def _llm_review(self, code: str) -> list[CritiqueIssue]:
        """LLM-based code review."""
        issues = []
        try:
            prompt = (
                "Review this code for quality issues. For each issue, provide:\n"
                "- Category (smell/readability/complexity)\n"
                "- Severity (minor/moderate/major)\n"
                "- Description\n\n"
                f"```\n{code[:3000]}\n```"
            )
            response = self.llm_client.generate(prompt=prompt, max_tokens=500)
            text = getattr(response, "text", str(response))

            # Parse simple issue format.
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("-") and ":" in line:
                    issues.append(CritiqueIssue(
                        category="llm_review",
                        severity="moderate",
                        description=line.lstrip("- "),
                    ))
        except Exception:
            pass
        return issues

    def _detect_smells(self, code: str) -> list[CritiqueIssue]:
        """Heuristic code smell detection."""
        issues = []
        lines = code.split("\n")

        # Long function detection.
        func_lengths: dict[str, int] = {}
        current_func = ""
        func_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("def "):
                if current_func and (i - func_start) > 50:
                    issues.append(CritiqueIssue(
                        category="smell", severity="moderate",
                        description=f"Function '{current_func}' is {i - func_start} lines (>50).",
                        suggestion="Consider breaking into smaller functions.",
                    ))
                current_func = stripped.split("(")[0].replace("def ", "")
                func_start = i

        # Deep nesting detection.
        max_indent = 0
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                max_indent = max(max_indent, indent)
        if max_indent > 24:  # 6+ levels
            issues.append(CritiqueIssue(
                category="smell", severity="moderate",
                description=f"Deep nesting detected (indent level {max_indent // 4}).",
                suggestion="Consider extracting helper functions or using guard clauses.",
            ))

        # God class detection.
        class_count = sum(1 for l in lines if l.strip().startswith("class "))
        method_count = sum(1 for l in lines if l.strip().startswith("def "))
        if class_count == 1 and method_count > 15:
            issues.append(CritiqueIssue(
                category="smell", severity="minor",
                description=f"Possible god class: 1 class with {method_count} methods.",
                suggestion="Consider splitting responsibilities.",
            ))

        return issues

    def _check_patterns(self, code: str) -> list[str]:
        """Check if code matches known patterns."""
        matched = []
        if self.pattern_manager:
            patterns = self.pattern_manager.get_patterns_multi(
                skills=["general"], domains=["general"], limit=10,
            )
            for p in patterns:
                content = getattr(p, "content", "")
                if content and any(
                    keyword in code.lower()
                    for keyword in content.lower().split()[:5]
                ):
                    matched.append(getattr(p, "id", ""))
        return matched

    def _score_readability(self, code: str) -> float:
        """Heuristic readability score."""
        lines = code.split("\n")
        if not lines:
            return 0.5

        score = 0.7  # Base.

        # Docstrings boost.
        if '"""' in code or "'''" in code:
            score += 0.1

        # Comment ratio.
        comments = sum(1 for l in lines if l.strip().startswith("#"))
        ratio = comments / max(len(lines), 1)
        if 0.05 <= ratio <= 0.3:
            score += 0.1

        # Average line length.
        avg_len = sum(len(l) for l in lines) / max(len(lines), 1)
        if avg_len < 80:
            score += 0.05

        return min(1.0, score)
