"""Layer 2 — LLM client with retry logic and template support.

Wraps LLM API calls with cost tracking, rate limiting, economy mode,
and YAML template-based prompting.
"""
from __future__ import annotations

import os
import time
import uuid
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


def make_anthropic_backend(api_key: Optional[str] = None) -> Callable[..., dict[str, Any]]:
    """Create a backend callable that uses the Anthropic SDK."""
    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file or environment.")

    client = anthropic.Anthropic(api_key=key)

    def backend(
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        messages = [{"role": "user", "content": user_prompt}]
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt or anthropic.NOT_GIVEN,
            messages=messages,
        )
        content = response.content[0].text if response.content else ""
        return {
            "content": content,
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "finish_reason": response.stop_reason or "stop",
        }

    return backend

from ..result import Result, LLMError, LLMErrorType
from ..types.common import LLMCallRecord
from ..types.enums import FinishReason


class LLMClient:
    """LLM API client with retry, templates, and cost tracking."""

    def __init__(
        self,
        default_model: str = "claude-sonnet-4-20250514",
        fallback_model: str = "claude-haiku-3-20250305",
        economy_model: str = "claude-haiku-3-20250305",
        max_retries: int = 3,
        timeout_seconds: int = 60,
        rate_limit_rpm: int = 60,
        cost_per_1k_prompt: float = 0.03,
        cost_per_1k_completion: float = 0.06,
        template_dir: Optional[Path] = None,
        backend: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> None:
        self._default_model = default_model
        self._fallback_model = fallback_model
        self._economy_model = economy_model
        self._max_retries = max_retries
        self._timeout = timeout_seconds
        self._rate_limit_rpm = rate_limit_rpm
        self._cost_prompt = cost_per_1k_prompt
        self._cost_completion = cost_per_1k_completion
        self._template_dir = template_dir
        self._backend = backend or self._default_backend
        self._economy_mode = False
        self._call_timestamps: list[float] = []
        self._total_calls = 0
        self._total_cost = 0.0
        self._templates: dict[str, dict] = {}

    def set_economy_mode(self, enabled: bool) -> None:
        self._economy_mode = enabled

    def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Result[LLMCallRecord, LLMError]:
        """Make an LLM completion request with retry logic."""
        effective_model = model or (
            self._economy_model if self._economy_mode else self._default_model
        )

        # Rate limiting
        self._enforce_rate_limit()

        last_error: Optional[LLMError] = None
        for attempt in range(self._max_retries + 1):
            try:
                start = time.monotonic()
                response = self._backend(
                    model=effective_model,
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency_ms = (time.monotonic() - start) * 1000

                prompt_tokens = response.get("prompt_tokens", len(prompt) // 4)
                completion_tokens = response.get("completion_tokens", len(response.get("content", "")) // 4)
                total_tokens = prompt_tokens + completion_tokens
                cost = (
                    (prompt_tokens / 1000) * self._cost_prompt
                    + (completion_tokens / 1000) * self._cost_completion
                )

                self._total_calls += 1
                self._total_cost += cost

                record = LLMCallRecord(
                    call_id=str(uuid.uuid4()),
                    cycle_number=0,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    model=effective_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    finish_reason=FinishReason(response.get("finish_reason", "stop")),
                    template_name=response.get("template_name", ""),
                    success=True,
                )
                return Result(value=record)

            except Exception as exc:
                last_error = LLMError(
                    error_type=LLMErrorType.SERVER_ERROR,
                    message=f"Attempt {attempt + 1} failed: {exc}",
                )
                if attempt < self._max_retries:
                    time.sleep(min(2 ** attempt, 30))
                continue

        # All retries exhausted — try fallback model
        if effective_model != self._fallback_model:
            return self.complete(
                prompt=prompt,
                system_prompt=system_prompt,
                model=self._fallback_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return Result(error=last_error or LLMError(
            error_type=LLMErrorType.SERVER_ERROR,
            message="All retries exhausted",
        ))

    def complete_text(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Return raw text content from the LLM. Used by meta-learning components."""
        effective_model = self._economy_model if self._economy_mode else self._default_model
        self._enforce_rate_limit()
        for attempt in range(self._max_retries + 1):
            try:
                response = self._backend(
                    model=effective_model,
                    system_prompt=system,
                    user_prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._total_calls += 1
                p_tok = response.get("prompt_tokens", len(prompt) // 4)
                c_tok = response.get("completion_tokens", len(response.get("content", "")) // 4)
                self._total_cost += (p_tok / 1000) * self._cost_prompt + (c_tok / 1000) * self._cost_completion
                return response.get("content", "")
            except Exception:
                if attempt == self._max_retries:
                    return ""
                time.sleep(min(2 ** attempt, 30))
        return ""

    def complete_with_template(
        self,
        template_name: str,
        variables: dict[str, Any],
        model: Optional[str] = None,
    ) -> Result[LLMCallRecord, LLMError]:
        """Complete using a YAML template."""
        template = self._load_template(template_name)
        if template is None:
            return Result(error=LLMError(
                error_type=LLMErrorType.INVALID_RESPONSE,
                message=f"Template not found: {template_name}",
            ))

        system_prompt = template.get("system_prompt", "")
        user_prompt = template.get("user_prompt", "")

        # Substitute variables
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            system_prompt = system_prompt.replace(placeholder, str(value))
            user_prompt = user_prompt.replace(placeholder, str(value))

        return self.complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=template.get("temperature", 0.0),
            max_tokens=template.get("max_tokens", 4096),
        )

    def get_cost_estimate(self, prompt: str, model: str) -> float:
        estimated_tokens = len(prompt) // 4
        return (estimated_tokens / 1000) * self._cost_prompt

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "total_cost_usd": self._total_cost,
            "economy_mode": self._economy_mode,
        }

    def _load_template(self, name: str) -> Optional[dict]:
        if name in self._templates:
            return self._templates[name]
        if self._template_dir:
            path = self._template_dir / f"{name}.yaml"
            if path.exists():
                with open(path) as f:
                    template = yaml.safe_load(f)
                self._templates[name] = template
                return template
        return None

    def _enforce_rate_limit(self) -> None:
        now = time.monotonic()
        self._call_timestamps = [
            t for t in self._call_timestamps if now - t < 60
        ]
        if len(self._call_timestamps) >= self._rate_limit_rpm:
            sleep_time = 60 - (now - self._call_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        self._call_timestamps.append(time.monotonic())

    @staticmethod
    def _default_backend(**kwargs: Any) -> dict[str, Any]:
        """Default stub backend — replace with actual API integration."""
        return {
            "content": "[LLM response placeholder — connect a real backend]",
            "prompt_tokens": len(kwargs.get("user_prompt", "")) // 4,
            "completion_tokens": 100,
            "finish_reason": "stop",
        }
