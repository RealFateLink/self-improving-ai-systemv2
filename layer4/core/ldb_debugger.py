"""ldb_debugger.py — Runtime trace debugger for precise error localization.

Layer 4 — v0.2.0.  Implements LDB-style (2402.16906) basic-block-level debugging.
Segments code into basic blocks, traces execution, identifies failing blocks.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class BasicBlock:
    """A basic block of code with entry/exit points."""
    block_id: int
    start_line: int
    end_line: int
    code: str
    block_type: str  # entry | loop | branch | return | normal


@dataclass(frozen=True)
class BlockTrace:
    """Execution trace for a single block."""
    block_id: int
    executed: bool
    variables: dict[str, Any]
    exception: str | None


@dataclass(frozen=True)
class DebugResult:
    """Result of LDB-style debugging."""
    candidate_id: str
    failing_block: BasicBlock | None
    error_location: int | None  # line number
    variable_states: dict[str, Any]
    suggestion: str


@dataclass
class LDBDebugger:
    """LLM Debugger via verifying runtime execution step-by-step.

    Based on "A Large Language Model Debugger via Verifying Runtime
    Execution Step-by-Step" (2402.16906).
    """

    sandbox: Any = None
    llm_client: Any = None

    def debug(
        self,
        candidate: Any,
        task: Any,
        execution_result: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Debug a failed candidate.

        Returns (True, ModuleResult) with DebugResult.
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            code = getattr(candidate, "code", "")
            cid = getattr(candidate, "candidate_id", "unknown")

            if execution_result.get("success", False):
                return True, ModuleResult(primary=None)

            # Parse into basic blocks
            blocks = self._segment_into_blocks(code)

            # Trace execution
            traces = self._trace_blocks(code, blocks, task)

            # Find failing block
            failing_block = None
            for block, trace in zip(blocks, traces):
                if trace.exception:
                    failing_block = block
                    break
                if not trace.executed and block.block_type == "return":
                    # Return block not reached = control flow issue
                    failing_block = block
                    break

            # If no block-level failure, use line-level error
            error_line = self._extract_error_line(execution_result.get("stderr", ""))

            # Generate suggestion
            suggestion = self._generate_suggestion(
                code, failing_block, error_line, execution_result.get("stderr", ""), task,
            )

            result = DebugResult(
                candidate_id=cid,
                failing_block=failing_block,
                error_location=error_line or (failing_block.start_line if failing_block else None),
                variable_states=traces[-1].variables if traces else {},
                suggestion=suggestion,
            )

            return True, ModuleResult(primary=result)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Debugging failed: {exc}",
                is_retryable=True,
            )

    def _segment_into_blocks(self, code: str) -> list[BasicBlock]:
        """Segment code into basic blocks."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        blocks = []
        current_start = 1
        block_id = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.FunctionDef)):
                # End current block before control structure
                if node.lineno > current_start:
                    blocks.append(BasicBlock(
                        block_id=block_id,
                        start_line=current_start,
                        end_line=node.lineno - 1,
                        code="",
                        block_type="normal",
                    ))
                    block_id += 1

                # The control structure itself
                end_line = getattr(node, 'end_lineno', node.lineno) or node.lineno
                block_type = "loop" if isinstance(node, (ast.For, ast.While)) else \
                            "branch" if isinstance(node, ast.If) else "normal"
                blocks.append(BasicBlock(
                    block_id=block_id,
                    start_line=node.lineno,
                    end_line=end_line,
                    code="",
                    block_type=block_type,
                ))
                block_id += 1
                current_start = end_line + 1

        # Trailing block
        lines = code.split("\n")
        if current_start <= len(lines):
            blocks.append(BasicBlock(
                block_id=block_id,
                start_line=current_start,
                end_line=len(lines),
                code="",
                block_type="return" if any("return" in l for l in lines[current_start-1:]) else "normal",
            ))

        return blocks

    def _trace_blocks(
        self,
        code: str,
        blocks: list[BasicBlock],
        task: Any,
    ) -> list[BlockTrace]:
        """Trace execution of each block using instrumented code."""
        traces = []

        # Instrument code with trace prints
        instrumented = self._instrument_code(code)

        if not self.sandbox:
            return [BlockTrace(b.block_id, True, {}, None) for b in blocks]

        # Run instrumented code
        test_code = getattr(task, "test_code", "") or getattr(task, "tests", "")
        result = self.sandbox.execute(
            code=instrumented,
            test_code=test_code,
            language="python",
        )

        # Parse trace output
        executed_blocks = set()
        variable_states = {}
        if result.get("success", False) or result.get("stdout", ""):
            for line in result.get("stdout", "").split("\n"):
                if line.startswith("__LDB_BLOCK__:"):
                    bid = int(line.split(":")[1])
                    executed_blocks.add(bid)
                elif line.startswith("__LDB_VAR__:"):
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        variable_states[parts[1]] = parts[2]

        for block in blocks:
            traces.append(BlockTrace(
                block_id=block.block_id,
                executed=block.block_id in executed_blocks,
                variables=dict(variable_states),
                exception=result.get("stderr", None) if block.block_id == max(executed_blocks, default=-1) else None,
            ))

        return traces

    def _instrument_code(self, code: str) -> str:
        """Add trace instrumentation to code."""
        lines = code.split("\n")
        instrumented = []
        block_id = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Detect block boundaries
            if stripped.startswith(("if ", "for ", "while ", "def ", "try:", "with ")):
                indent = len(line) - len(line.lstrip())
                instrumented.append(" " * indent + f"print('__LDB_BLOCK__:{block_id}')")
                block_id += 1
            # Detect variable assignments
            if "=" in stripped and not stripped.startswith("#"):
                var_name = stripped.split("=")[0].strip()
                if var_name.isidentifier():
                    indent = len(line) - len(line.lstrip())
                    instrumented.append(line)
                    instrumented.append(" " * indent + f"print(f'__LDB_VAR__:{var_name}:{{{var_name}}}')")
                    continue
            instrumented.append(line)

        return "\n".join(instrumented)

    def _extract_error_line(self, stderr: str) -> int | None:
        """Extract line number from Python traceback."""
        match = re.search(r'File "[^"]+", line (\d+)', stderr)
        if match:
            return int(match.group(1))
        return None

    def _generate_suggestion(
        self,
        code: str,
        failing_block: BasicBlock | None,
        error_line: int | None,
        stderr: str,
        task: Any,
    ) -> str:
        """Generate fix suggestion using LLM or heuristics."""
        if not self.llm_client:
            return self._heuristic_suggestion(stderr, error_line)

        try:
            block_info = ""
            if failing_block:
                block_info = f"\nFailing block (lines {failing_block.start_line}-{failing_block.end_line}, type: {failing_block.block_type}):"

            prompt = f"""The following code failed. Debug and suggest a fix.

Code:
```{code}```

Error:
{stderr}
{block_info}

Line with error: {error_line or 'unknown'}

Provide a concise fix suggestion (1-2 sentences).
"""
            response = self.llm_client.complete(
                prompt=prompt,
                system_prompt="You are an expert debugger. Be concise and specific.",
                max_tokens=200,
                temperature=0.1,
            )
            if response.is_ok():
                text = response.value.content if hasattr(response.value, "content") else str(response.value)
                return text.strip()
        except Exception:
            pass

        return self._heuristic_suggestion(stderr, error_line)

    def _heuristic_suggestion(self, stderr: str, error_line: int | None) -> str:
        """Generate heuristic suggestion based on error type."""
        stderr_lower = stderr.lower()
        if "nameerror" in stderr_lower:
            return f"Line {error_line or '?'}: Variable not defined. Check spelling and scope."
        if "typeerror" in stderr_lower:
            return f"Line {error_line or '?'}: Type mismatch. Check argument types."
        if "indexerror" in stderr_lower:
            return "Index out of bounds. Check list/string length before indexing."
        if "keyerror" in stderr_lower:
            return "Key not found in dict. Use .get() or check key existence."
        if "attributeerror" in stderr_lower:
            return "Attribute not found. Check object type and attribute name."
        if "indentationerror" in stderr_lower:
            return "Indentation error. Ensure consistent use of spaces."
        if "timeout" in stderr_lower:
            return "Execution timed out. Check for infinite loops or excessive recursion."
        return f"Error at line {error_line or '?'}. Review the error message and fix accordingly."
