"""LiteLLM JSON annotation client.

The pipeline talks to any LiteLLM-supported provider through environment
variables. Azure OpenAI example (put these in .env / the shell):

    LITELLM_MODEL=azure/gpt-4o          # azure/<deployment-name>
    AZURE_API_KEY=<key>
    AZURE_API_BASE=https://<resource>.openai.azure.com/
    AZURE_API_VERSION=2024-08-01-preview

LLM annotation is enabled whenever LITELLM_MODEL is set and
TAOTCM_USE_LLM is not "0". Without it the pipeline falls back to the
deterministic heuristic annotators so CI and offline runs stay green.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from canon_tcm_hermes.llm.json_repair import repair_json
from canon_tcm_hermes.validators.schema_validator import schema_errors


class LLMError(RuntimeError):
    """Raised when the LLM cannot produce schema-valid JSON within budget."""


@dataclass
class LLMSettings:
    model: str = field(default_factory=lambda: os.getenv("LITELLM_MODEL", ""))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "4")))
    max_concurrency: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENCY", "5")))
    temperature: float = 0.1
    max_tokens: int = 4096


def llm_enabled() -> bool:
    return bool(os.getenv("LITELLM_MODEL")) and os.getenv("TAOTCM_USE_LLM", "1") != "0"


_semaphore: threading.Semaphore | None = None
_semaphore_lock = threading.Lock()


def _concurrency_gate(settings: LLMSettings) -> threading.Semaphore:
    global _semaphore
    with _semaphore_lock:
        if _semaphore is None:
            _semaphore = threading.Semaphore(max(settings.max_concurrency, 1))
        return _semaphore


def _completion_text(settings: LLMSettings, messages: list[dict[str, str]]) -> str:
    from litellm import completion

    with _concurrency_gate(settings):
        response = completion(
            model=settings.model,
            messages=messages,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
    return response.choices[0].message.content or ""


def complete_json(
    system_prompt: str,
    user_prompt: str,
    schema_name: str | None = None,
    settings: LLMSettings | None = None,
    raw_sink: list[str] | None = None,
    validate: Callable[[Any], list[str]] | None = None,
) -> Any:
    """Call the LLM and return parsed JSON, retrying with error feedback.

    Retry policy per protocol L22: JSON parse errors are retried with the
    parser message; schema validation errors are retried with the
    validation diff; exhausting the retry budget raises LLMError so the
    caller can record the failure in errors.jsonl (never silently drop).

    `validate` overrides `schema_name`: it receives the parsed JSON and
    returns a list of error strings (empty = valid). Use it when the raw
    LLM payload is only schema-valid after caller-side post-processing.
    """
    settings = settings or LLMSettings()
    if not settings.model:
        raise LLMError("LITELLM_MODEL is not configured")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_error = "unknown"
    for _attempt in range(max(settings.max_retries, 1)):
        try:
            raw = _completion_text(settings, messages)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 — provider/binding crashes
            # (e.g. pyo3 PanicException from a broken native dependency) must
            # not break the heuristic fallback path; they are BaseException.
            last_error = f"llm_call_failed: {exc}"
            continue
        if raw_sink is not None:
            raw_sink.append(raw)
        try:
            data = repair_json(raw)
        except Exception as exc:
            last_error = f"json_parse_failed: {exc}"
            messages = messages[:2] + [
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content": f"Your previous reply was not valid JSON ({exc}). Return ONLY the corrected JSON object, no prose, no code fences."},
            ]
            continue
        if validate is not None:
            errors = list(validate(data))
        elif schema_name is not None:
            errors = schema_errors(data, schema_name)
        else:
            return data
        if not errors:
            return data
        last_error = "schema_validation_failed: " + "; ".join(errors[:5])
        messages = messages[:2] + [
            {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)[:4000]},
            {"role": "user", "content": "Your previous JSON failed schema validation:\n- " + "\n- ".join(errors[:10]) + "\nReturn ONLY the corrected JSON object."},
        ]
    raise LLMError(last_error)


async def call_llm_json(model: str | None, system_prompt: str, user_prompt: str, schema_name: str, temperature: float = 0.1, max_tokens: int = 4096) -> Any:
    """Async wrapper kept for protocol L22 compatibility."""
    import asyncio

    settings = LLMSettings(model=model or os.getenv("LITELLM_MODEL", ""), temperature=temperature, max_tokens=max_tokens)
    return await asyncio.to_thread(complete_json, system_prompt, user_prompt, schema_name, settings)
