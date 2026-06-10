from __future__ import annotations

import os
from typing import Any

from canon_tcm_hermes.llm.json_repair import repair_json
from canon_tcm_hermes.validators.schema_validator import validate_schema_file

async def call_llm_json(model: str | None, system_prompt: str, user_prompt: str, schema_name: str, temperature: float = 0.1, max_tokens: int = 4096) -> Any:
    """Call LiteLLM and validate JSON output.

    Azure example environment:
    LITELLM_MODEL=azure/gpt-4o, AZURE_API_KEY, AZURE_API_BASE,
    AZURE_API_VERSION=2024-08-01-preview.
    """
    from litellm import acompletion
    response = await acompletion(
        model=model or os.getenv("LITELLM_MODEL", "azure/gpt-4o"),
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    raw = response.choices[0].message.content
    data = repair_json(raw)
    validate_schema_file(data, schema_name)
    return data
