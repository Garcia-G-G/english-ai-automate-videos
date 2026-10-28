import json
from types import SimpleNamespace

import pytest


class _Tracker:
    def __init__(self):
        self.entries = []

    def _add_entry(self, api_type, model, cost, label, details):   # llm.record, one row per attempt
        assert api_type == "openrouter_chat"
        self.entries.append(details)


def _response(payload, prompt_tokens, completion_tokens):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


def test_duplicate_quiz_retry_records_usage_for_both_model_attempts(monkeypatch):
    from script_generator import generate_script_from_prompt

    duplicate = {
        "question": "Choose",
        "options": {"A": "same", "B": "same", "C": "third", "D": "fourth"},
        "correct": "A",
        "explanation": "解释",
        "questions": [],
        "full_script": "请选择 same。",
        "translations": {"same": "相同"},
    }
    unique = {
        **duplicate,
        "options": {"A": "one", "B": "two", "C": "three", "D": "four"},
    }
    responses = iter([_response(duplicate, 10, 20), _response(unique, 30, 40)])
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: next(responses))
        )
    )
    tracker = _Tracker()
    monkeypatch.setattr("cost_tracker.get_tracker", lambda: tracker)
    monkeypatch.setattr("script_generator.validate_and_clean_script", lambda script, *a, **k: script)
    monkeypatch.setattr("script_generator.validate_script", lambda *a, **k: None)

    result = generate_script_from_prompt(
        "category", {"id": "topic"}, "quiz", "prompt", "system", client=client
    )

    assert result["options"] == unique["options"]
    assert [(e["prompt_tokens"], e["completion_tokens"]) for e in tracker.entries] == [
        (10, 20),
        (30, 40),
    ]


def test_retry_usage_is_recorded_even_when_retry_payload_is_malformed(monkeypatch):
    from script_generator import generate_script_from_prompt

    duplicate = {
        "options": {"A": "same", "B": "same", "C": "third", "D": "fourth"},
        "questions": [],
    }
    malformed = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=8),
    )
    responses = iter([_response(duplicate, 5, 6), malformed])
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: next(responses))
        )
    )
    tracker = _Tracker()
    monkeypatch.setattr("cost_tracker.get_tracker", lambda: tracker)
    monkeypatch.setattr("script_generator.validate_and_clean_script", lambda script, *a, **k: script)
    monkeypatch.setattr("script_generator.validate_script", lambda *a, **k: None)

    generate_script_from_prompt(
        "category", {"id": "topic"}, "quiz", "prompt", "system", client=client
    )

    assert len(tracker.entries) == 2
    assert tracker.entries[-1]["prompt_tokens"] == 7


def test_a_script_the_validator_refuses_gets_one_repair_round_with_the_errors(monkeypatch):
    import script_generator as SG
    from script_schema import ScriptValidationError
    prompts = []

    def fake(category, topic, video_type, prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            raise ScriptValidationError("how_do_you_say", ["emoji: '1️⃣' is 3 code points"])
        return {"ok": True}
    monkeypatch.setattr(SG, "_generate", fake)
    monkeypatch.setattr("channel_insights.brief", lambda vt, **k: "BRIEF")
    assert SG.generate_script("c", {"id": "t"}, "how_do_you_say") == {"ok": True}
    assert "BRIEF" in prompts[0] and "1️⃣" in prompts[1] and len(prompts) == 2
