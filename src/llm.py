"""Every LLM call goes through OpenRouter: one key (OPENROUTER_API_KEY), one bill.

OpenAI's own API is not used any more (2026-10-27: its key is dead on purpose). OpenRouter speaks
the OpenAI chat-completions protocol, so the `openai` SDK works unchanged with its base_url.

The model per task is config.yaml `llm.models.<task>` (else `llm.model`), so a better or cheaper
model is a config change, not a code change.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
KEY_NAME = "OPENROUTER_API_KEY"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def _settings() -> Dict:
    import queue_priority
    return queue_priority._config().get("llm") or {}       # parsed once per change of config.yaml


def model(task: str) -> str:
    """The OpenRouter model id for a task («script», «metadata», «platform_metadata»)."""
    s = _settings()
    return (s.get("models") or {}).get(task) or s.get("model") or DEFAULT_MODEL


def client():
    """An OpenAI-SDK client pointed at OpenRouter. Raises (in Spanish) when the key is missing."""
    import secret_store
    key = secret_store.get(KEY_NAME)
    if not key:
        raise EnvironmentError(f"Falta {KEY_NAME} (entorno, .env o el Llavero «english-ai-videos»).")
    from openai import OpenAI                               # lazy: 0.3 s the panel need not pay at start
    return OpenAI(base_url=BASE_URL, api_key=key, timeout=120.0, max_retries=2,
                  default_headers={"X-Title": "english-ai-videos"})


def record(response: Any, model_id: str, label: str) -> float:
    """One row in output/costs/ (api_type «openrouter_chat»), at the cost OpenRouter reports."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    extra = getattr(usage, "model_extra", None) or {}
    cost = float(getattr(usage, "cost", None) or extra.get("cost") or 0.0)
    from cost_tracker import get_tracker
    get_tracker()._add_entry("openrouter_chat", model_id, round(cost, 6), label, {
        "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.prompt_tokens + usage.completion_tokens})
    return cost


def chat(task: str, messages, *, label: Optional[str] = None, client_=None, **kwargs):
    """One chat completion for `task`, recorded. Returns the SDK response."""
    model_id = model(task)
    response = (client_ or client()).chat.completions.create(
        model=model_id, messages=messages, extra_body={"usage": {"include": True}}, **kwargs)
    try:
        record(response, model_id, label or task)
    except Exception:                                       # noqa: BLE001 — a ledger row never fails a call
        logger.exception("llm: could not record the cost of %s", model_id)
    return response


def json_content(response) -> Dict:
    """The reply's JSON object. Some models (Claude via OpenRouter) ignore response_format
    json_object and wrap the object in a ```json fence; this reads both."""
    text = (response.choices[0].message.content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return json.loads(fenced.group(1) if fenced else text)
