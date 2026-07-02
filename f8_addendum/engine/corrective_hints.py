"""F8 Addendum — A-9: Self-Correcting Error Messages.

Every error message gets two parts: diagnostic (what went wrong)
and corrective guidance (how to fix it). Hints never include the
solution — guidance only.
~70 lines | Integrates with L4 failure_analyzer and L6 agent feedback.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_DIAGNOSTIC_LENGTH = 500


@dataclass(frozen=True)
class CorrectedError:
    """Error message with diagnostic and corrective guidance."""

    diagnostic: str
    """Part 1: what went wrong (raw error, truncated to 500 chars)."""

    corrective_hint: Optional[str]
    """Part 2: how to fix it (guidance, NOT solution).
    Injected into generator's next prompt as <corrective_guidance>."""

    hint_source: str = ""
    """How the hint was generated: 'pattern_match', 'llm_generated', 'none'."""


# Known error signatures → corrective hints (pattern-based)
ERROR_HINT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"NameError.*name '(\w+)' is not defined"),
        "Variable '{0}' is used but not defined in scope. "
        "Common fix: pass as parameter or check spelling.",
    ),
    (
        re.compile(r"IndexError.*list index out of range"),
        "List access exceeds bounds. Check for empty list or "
        "off-by-one in loop range.",
    ),
    (
        re.compile(r"TypeError.*takes \d+ positional argument"),
        "Function call has wrong number of arguments. Check "
        "the function signature and call site.",
    ),
    (
        re.compile(r"AttributeError.*has no attribute '(\w+)'"),
        "Object doesn't have attribute '{0}'. Check the type "
        "and available methods/properties.",
    ),
    (
        re.compile(r"ZeroDivisionError"),
        "Division by zero. Add a guard: check denominator before dividing.",
    ),
    (
        re.compile(r"RecursionError|maximum recursion depth"),
        "Infinite recursion detected. Check base case and ensure "
        "recursive calls converge.",
    ),
    (
        re.compile(r"TimeoutError|timed out|Timeout"),
        "Solution likely has high complexity. Look for O(n^2) or "
        "worse algorithms and optimize.",
    ),
    (
        re.compile(r"expected (\[?\]) but got None"),
        "Returning None instead of expected value. Check for missing "
        "return statement or early-return for empty input.",
    ),
    (
        re.compile(r"SyntaxError"),
        "Code has a syntax error. Check for unclosed brackets, "
        "missing colons, or invalid indentation.",
    ),
    (
        re.compile(r"ImportError|ModuleNotFoundError"),
        "Missing import or module. Ensure all dependencies are "
        "imported at the top of the file.",
    ),
]

# Patterns that indicate a hint contains actual code (forbidden)
CODE_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```"),
    re.compile(r"def \w+\("),
    re.compile(r"class \w+[:(]"),
    re.compile(r"import \w+"),
    re.compile(r"for \w+ in "),
    re.compile(r"if __name__"),
]


class CorrectiveHintGenerator:
    """Generates corrective guidance for error messages.

    Sources:
      1. Pattern matching against known error signatures.
      2. LLM-generated guidance for novel errors.

    CONSTRAINT: Hints must NEVER include the solution.
    Post-generation filter rejects hints containing code blocks.
    """

    def __init__(self, ledger: Any, llm_client: Any, config: Any) -> None:
        self._ledger = ledger
        self._llm = llm_client
        self._config = config

    def generate(
        self,
        error_messages: list[str],
        generated_code: str = "",
    ) -> CorrectedError:
        """Generate a corrected error with diagnostic and hint.

        Steps:
          1. Truncate diagnostic.
          2. Try pattern match.
          3. If no match, try LLM generation.
          4. Validate hint doesn't contain code.
        """
        # Part 1: Diagnostic
        raw = "\n".join(error_messages)
        diagnostic = raw[:MAX_DIAGNOSTIC_LENGTH]

        # Part 2: Try pattern match
        hint, source = self._try_pattern_match(raw)

        # Part 3: Try LLM if no pattern match
        if hint is None:
            hint, source = self._try_llm_hint(raw, generated_code)

        # Part 4: Validate hint
        if hint and self._hint_contains_code(hint):
            logger.warning("Hint contained code, rejecting: %s", hint[:100])
            hint = None
            source = "rejected"

        return CorrectedError(
            diagnostic=diagnostic,
            corrective_hint=hint,
            hint_source=source,
        )

    def record_successful_hint(
        self,
        hint: str,
        error_signature: str,
    ) -> None:
        """Record when a hint led to a successful fix.

        The hint→fix pair becomes a pattern candidate.
        """
        self._ledger.insert_pattern_candidate(
            source="corrective_hint",
            description=f"Error: {error_signature[:100]} → Hint: {hint[:200]}",
            skill_tags=(),
        )
        logger.info("Recorded successful hint as pattern candidate")

    # ── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _try_pattern_match(error_text: str) -> tuple[Optional[str], str]:
        """Try to match error against known patterns."""
        for pattern, hint_template in ERROR_HINT_PATTERNS:
            match = pattern.search(error_text)
            if match:
                # Fill in captured groups
                groups = match.groups()
                hint = hint_template
                for i, group in enumerate(groups):
                    hint = hint.replace(f"{{{i}}}", group)
                return hint, "pattern_match"
        return None, "none"

    def _try_llm_hint(
        self, error_text: str, generated_code: str
    ) -> tuple[Optional[str], str]:
        """Generate hint using LLM for novel errors."""
        if self._llm is None:
            return None, "none"

        prompt = (
            "Given this error in generated code:\n"
            f"{error_text[:300]}\n\n"
            "Provide a SHORT corrective hint (1-2 sentences) about how "
            "to fix it. Do NOT include any code. Only provide guidance.\n"
            "Example: 'Add a guard for empty input before the loop.'\n"
            "Hint:"
        )

        try:
            response = self._llm.generate(
                prompt=prompt,
                max_tokens=100,
            )
            hint = getattr(response, "text", str(response)).strip()
            if hint and len(hint) < 300:
                return hint, "llm_generated"
        except Exception as exc:
            logger.debug("LLM hint generation failed: %s", exc)

        return None, "none"

    @staticmethod
    def _hint_contains_code(hint: str) -> bool:
        """Check if a hint contains actual code (forbidden)."""
        for pattern in CODE_BLOCK_PATTERNS:
            if pattern.search(hint):
                return True
        return False
