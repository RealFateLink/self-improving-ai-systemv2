"""llm_backends.py — Unified LLM backend interface for Anthropic, DeepSeek, OpenAI.

Layer 2 — v0.2.0.  Replaces hardcoded Anthropic backend with pluggable backends.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class LLMBackend(ABC):
    """Abstract base for all LLM API backends."""

    @abstractmethod
    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a completion request. Return standardized dict."""
        ...

    @abstractmethod
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate USD cost for a call."""
        ...


class AnthropicBackend(LLMBackend):
    """Anthropic Claude API backend."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        import anthropic
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=key)
        self._cost_per_1k_prompt = 0.003
        self._cost_per_1k_completion = 0.015

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict[str, Any]:
        import anthropic
        messages = [{"role": "user", "content": user_prompt}]
        response = self._client.messages.create(
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

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            (prompt_tokens / 1000) * self._cost_per_1k_prompt
            + (completion_tokens / 1000) * self._cost_per_1k_completion
        )


class DeepSeekBackend(LLMBackend):
    """DeepSeek API backend."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        from openai import OpenAI
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set")
        self._client = OpenAI(api_key=key, base_url=base_url or "https://api.deepseek.com/v1")
        self._cost_per_1k_prompt = 0.00027  # DeepSeek-V3 pricing
        self._cost_per_1k_completion = 0.0011

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return {
            "content": choice.message.content or "",
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "finish_reason": choice.finish_reason or "stop",
        }

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            (prompt_tokens / 1000) * self._cost_per_1k_prompt
            + (completion_tokens / 1000) * self._cost_per_1k_completion
        )


class OpenAIBackend(LLMBackend):
    """OpenAI API backend."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        from openai import OpenAI
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        self._client = OpenAI(api_key=key)
        self._cost_per_1k_prompt = 0.005   # GPT-4o-mini default
        self._cost_per_1k_completion = 0.015

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return {
            "content": choice.message.content or "",
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "finish_reason": choice.finish_reason or "stop",
        }

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            (prompt_tokens / 1000) * self._cost_per_1k_prompt
            + (completion_tokens / 1000) * self._cost_per_1k_completion
        )


def make_backend(provider: str = "anthropic", **kwargs: Any) -> LLMBackend:
    """Factory: create backend by provider name."""
    provider = provider.lower()
    if provider == "anthropic":
        return AnthropicBackend(**kwargs)
    if provider == "deepseek":
        return DeepSeekBackend(**kwargs)
    if provider in ("openai", "azure"):
        return OpenAIBackend(**kwargs)
    raise ValueError(f"Unknown LLM provider: {provider}")
