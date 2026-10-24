import copy
import json
from types import SimpleNamespace

import pytest

from script_schema import validate_script
from studio.creation import AuthorFailure, AuthorResult, ScriptAuthor
from studio.models import CreationRequest


VIDEO_TYPES = (
    "educational", "quiz", "true_false", "fill_blank",
    "pronunciation", "vocabulary",
)


def request(*, audience="adults", mode="auto", video_type="educational", **values):
    data = {
        "market": "bilibili",
        "native_language": "zh-Hans",
        "learning_language": "en",
        "audience": audience,
        "mode": mode,
        "idea": "在机场自然地寻求帮助",
        "video_type": video_type,
    }
    data.update(values)
    return CreationRequest(**data)


def profile(audience="adults"):
    children = audience == "children"
    return {
        "profile_schema_version": 1,
        "audience": {
            "profile_schema_version": 1,
            "audience": audience,
            "name": audience,
            "content": {
                "categories": ["travel", "pronunciation"],
                "default_type": "educational",
            },
            "editorial": {
                "tone": (
                    "age-appropriate without exaggerated infantilization"
                    if children else "natural conversational instruction"
                ),
                "pacing": "clear with purposeful repetition" if children else "direct",
                "interaction_style": "restrained rewards" if children else "adult contexts",
                "child_safety": children,
            },
            "metadata": {
                "hashtag_seed": ["KidsEnglish", "英语启蒙"]
                if children else ["LearnEnglish", "英语学习"]
            },
        },
        "workspace": {
            "profile_schema_version": 1,
            "workspace_id": "bilibili_zh_hans_en",
            "market": "bilibili",
            "native_language": "zh-Hans",
            "learning_language": "en",
            "editorial": {"explanation_language": "zh-Hans"},
            "metadata": {"title_language": "zh-Hans", "hashtag_seed": ["英语学习"]},
            "subtitles": {"bilingual": True, "primary_language": "zh-Hans"},
        },
        "voice": {
            "profile_schema_version": 1,
            "workspace_id": "bilibili_zh_hans_en",
            "audience": audience,
            "locale": "zh-Hans",
            "provider": "elevenlabs",
            "voice_id": "MandarinVoice123456789",
            "traits": ["female", "natural"],
            "source": "cell_environment",
        },
    }


def representative(video_type):
    base = {
        "type": video_type,
        "full_script": "今天学习一个实用表达，并练习自然的英语例句。",
        "video_title": "一个真正实用的英语表达",
        "video_description": "用自然中文讲清英语用法。",
        "hashtags": ["#英语学习", "#学英语", "#实用英语", "#LearnEnglish", "#英语口语"],
    }
    fields = {
        "educational": {
            "hook": "这个表达在机场特别实用。",
            "english_phrases": ["Could you help me?"],
            "translations": {"Could you help me?": "你能帮我吗？"},
            "tip": "把整句作为一个语块来记。",
            "cta": "试着用它问一个真实问题。",
        },
        "quiz": {
            "question": "哪一句最适合礼貌求助？",
            "options": {"A": "Help me", "B": "Could you help me?", "C": "Go away", "D": "I know"},
            "correct": "B",
            "explanation": "B 更礼貌，也更适合真实交流。",
            "translations": {"Could you help me?": "你能帮我吗？"},
        },
        "true_false": {
            "statement": "Could you help me 是礼貌求助。",
            "correct": True,
            "explanation": "正确，这个表达自然又礼貌。",
            "translations": {"Could you help me?": "你能帮我吗？"},
        },
        "fill_blank": {
            "sentence": "Could you ___ me?",
            "options": ["help", "helps", "helped", "helping"],
            "correct": "help",
            "blank_position": "help",
            "explanation": "情态动词后使用动词原形。",
            "translation": "你能帮我吗？",
        },
        "pronunciation": {
            "word": "comfortable",
            "phonetic": "KUMF-tuh-buhl",
            "common_mistake": "不要逐个字母生硬地读。",
            "tip": "注意中间音节会弱化。",
            "translation": "舒服的",
        },
        "vocabulary": {
            "title": "机场实用词汇",
            "difficulty": "medio",
            "pairs": [
                {"spanish": "登机口", "english": "gate"},
                {"spanish": "行李", "english": "luggage"},
                {"spanish": "护照", "english": "passport"},
                {"spanish": "航班", "english": "flight"},
                {"spanish": "延误", "english": "delay"},
                {"spanish": "安检", "english": "security check"},
            ],
            "translations": {"gate": "登机口"},
            "english_phrases": ["gate", "luggage"],
        },
    }
    return {**base, **fields[video_type]}


class Tracker:
    def __init__(self):
        self.entries = [{"api_type": "old", "cost_usd": 8.0}]

    def log_openai_chat(self, prompt_tokens, completion_tokens, model, label):
        self.entries.append({
            "api_type": "openai_chat",
            "cost_usd": 0.001,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "label": label,
        })


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_exact_nested_identities_are_consumed_before_model_invocation(audience):
    seen = {}
    from studio.bilibili import BilibiliScriptAuthor

    def generate(**kwargs):
        seen.update(kwargs)
        return representative("educational")

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport help"}),
        generator=generate,
        tracker_getter=Tracker,
    )
    result = author.generate(request(audience=audience), profile(audience))

    assert isinstance(author, ScriptAuthor)
    assert isinstance(result, AuthorResult)
    assert seen["video_type"] == "educational"
    assert "bilibili_zh_hans_en" in seen["prompt"]
    assert audience in seen["prompt"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("workspace", "market"), "youtube"),
        (("workspace", "native_language"), "es"),
        (("workspace", "workspace_id"), "wrong"),
        (("audience", "audience"), "children"),
        (("voice", "locale"), "es"),
        (("voice", "workspace_id"), "wrong"),
        (("voice", "audience"), "children"),
    ],
)
def test_profile_identity_mismatch_rejects_before_model(path, value):
    calls = []
    broken = profile()
    broken[path[0]][path[1]] = value
    from studio.bilibili import BilibiliScriptAuthor

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport"}),
        generator=lambda **kwargs: calls.append("model"),
        tracker_getter=lambda: calls.append("tracker"),
    )
    with pytest.raises(ValueError, match=r"\.".join(path)):
        author.generate(request(), broken)
    assert calls == []


def test_youtube_request_is_rejected_before_selection_or_model():
    calls = []
    youtube = CreationRequest(audience="adults", mode="auto", idea="actually")
    from studio.bilibili import BilibiliScriptAuthor

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: calls.append("select"),
        generator=lambda **kwargs: calls.append("model"),
        tracker_getter=lambda: calls.append("tracker"),
    )
    with pytest.raises(ValueError, match="supports only bilibili"):
        author.generate(youtube, profile())
    assert calls == []


def test_directed_request_preserves_all_editorial_controls_in_prompt():
    seen = {}
    topic = {"topic": "asking for help", "examples": ["Could you help me?"]}
    from studio.bilibili import BilibiliScriptAuthor

    author = BilibiliScriptAuthor(
        topic_finder=lambda category, name: topic,
        generator=lambda **kwargs: seen.update(kwargs) or representative("quiz"),
        tracker_getter=Tracker,
    )
    directed = request(
        mode="directed", video_type="quiz", category="travel", topic="asking for help",
        learning_objective="在机场礼貌求助", learner_level="A2",
        duration_min_seconds=35, duration_max_seconds=55,
        tone="calm", voice_id="MandarinVoiceOverride123", background="library",
        notes="避免夸张承诺",
    )
    original = directed.model_copy(deep=True)
    author.generate(directed, profile())

    for value in (
        "在机场礼貌求助", "A2", "35", "55", "calm",
        "MandarinVoiceOverride123", "library", "避免夸张承诺",
    ):
        assert value in seen["prompt"]
    assert "asking for help" in seen["prompt"]
    assert directed == original


@pytest.mark.parametrize("video_type", VIDEO_TYPES)
def test_all_six_types_return_schema_valid_unicode_without_spanish_policy(video_type):
    seen = {}
    source = representative(video_type)
    original = copy.deepcopy(source)
    from studio.bilibili import BilibiliScriptAuthor

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport help"}),
        generator=lambda **kwargs: seen.update(kwargs) or source,
        tracker_getter=Tracker,
    )
    result = author.generate(request(video_type=video_type), profile())

    validate_script(result.script, video_type)
    assert result.script == original
    policy_text = seen["prompt"] + seen["system_instruction"]
    for forbidden in ("AprendeIngles", "hispanohablantes", "Tres... dos... uno", "翻译西班牙语脚本"):
        assert forbidden not in policy_text
    assert "简体中文" in policy_text
    assert "英语例句" in policy_text
    assert "Bilibili" in policy_text


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_prompt_carries_distinct_audience_policy_without_infantilizing(audience):
    seen = {}
    from studio.bilibili import BilibiliScriptAuthor

    BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport"}),
        generator=lambda **kwargs: seen.update(kwargs) or representative("educational"),
        tracker_getter=Tracker,
    ).generate(request(audience=audience), profile(audience))

    assert profile(audience)["audience"]["editorial"]["tone"] in seen["prompt"]
    assert str(audience == "children").lower() in seen["prompt"].lower()
    assert "幼稚化" in seen["prompt"]


def test_unicode_and_only_new_model_cost_survive_author_result():
    tracker = Tracker()
    from studio.bilibili import BilibiliScriptAuthor

    def generate(**kwargs):
        tracker.entries.append({
            "api_type": "openai_chat", "cost_usd": 0.007,
            "model": "gpt-4o-mini", "label": "script_quiz",
        })
        return representative("quiz")

    result = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    ).generate(request(video_type="quiz"), profile())

    assert result.script["question"] == "哪一句最适合礼貌求助？"
    assert [cost.amount for cost in result.costs] == [0.007]


def test_charged_model_failure_preserves_cost_and_cause():
    tracker = Tracker()
    cause = RuntimeError("model unavailable after charge")
    from studio.bilibili import BilibiliScriptAuthor

    def generate(**kwargs):
        tracker.entries.append({"api_type": "openai_chat", "cost_usd": 0.009})
        raise cause

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    )
    with pytest.raises(AuthorFailure) as raised:
        author.generate(request(), profile())
    assert raised.value.cause is cause
    assert [cost.amount for cost in raised.value.costs] == [0.009]


@pytest.mark.parametrize("failure", ["parse", "schema"])
def test_real_shared_parse_and_schema_failures_preserve_usage_cost(monkeypatch, failure):
    tracker = Tracker()
    content = "not JSON" if failure == "parse" else json.dumps({
        "type": "educational", "full_script": "这段旁白足够长但缺少必要字段。"
    }, ensure_ascii=False)
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response)
        )
    )
    monkeypatch.setattr("cost_tracker.get_tracker", lambda: tracker)
    from script_generator import ZH_HANS_CLEANUP_POLICY, generate_script_from_prompt
    from studio.bilibili import BilibiliScriptAuthor

    def generate(**kwargs):
        return generate_script_from_prompt(
            **kwargs, client=client, cleanup_policy=ZH_HANS_CLEANUP_POLICY
        )

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "airport"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    )
    with pytest.raises(AuthorFailure) as raised:
        author.generate(request(), profile())

    assert raised.value.cause.__class__.__name__ == (
        "JSONDecodeError" if failure == "parse" else "ScriptValidationError"
    )
    assert [cost.amount for cost in raised.value.costs] == [0.001]


def test_inputs_and_repeated_results_are_independent():
    selected = {"topic": "airport", "examples": ["Could you help me?"]}
    source = representative("educational")
    original = copy.deepcopy((selected, source, profile()))
    from studio.bilibili import BilibiliScriptAuthor

    author = BilibiliScriptAuthor(
        random_topic=lambda **kwargs: ("travel", selected),
        generator=lambda **kwargs: copy.deepcopy(source),
        tracker_getter=Tracker,
    )
    supplied_profile = profile()
    first = author.generate(request(), supplied_profile)
    second = author.generate(request(), supplied_profile)
    first.script["translations"]["Could you help me?"] = "changed"

    assert second.script["translations"]["Could you help me?"] == "你能帮我吗？"
    assert selected == original[0]
    assert source == original[1]
    assert supplied_profile == original[2]


def test_shared_model_seam_parses_validates_and_logs_unicode(monkeypatch):
    tracker = Tracker()
    payload = representative("educational")
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))],
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response)
        )
    )
    monkeypatch.setattr("cost_tracker.get_tracker", lambda: tracker)
    from script_generator import ZH_HANS_CLEANUP_POLICY, generate_script_from_prompt

    result = generate_script_from_prompt(
        "travel", {"id": "airport"}, "educational",
        prompt="请生成简体中文解释和英语例句",
        system_instruction="你是一位严谨自然的英语老师。",
        client=client,
        cleanup_policy=ZH_HANS_CLEANUP_POLICY,
    )

    assert result["hook"] == "这个表达在机场特别实用。"
    validate_script(result, "educational")
    assert tracker.entries[-1]["api_type"] == "openai_chat"
    assert "#AprendeIngles" not in result["hashtags"]
    assert "#英语学习" in result["hashtags"]


def test_default_cleanup_policy_preserves_spanish_countdown_marks_and_metadata():
    from script_generator import validate_and_clean_script

    source = {
        "type": "quiz",
        "question": "Which answer is correct?",
        "options": {"A": "one", "B": "two", "C": "three", "D": "four"},
        "correct": "D",
        "explanation": "This is correct!",
        "full_script": "Think carefully. Three... two... one... choose four.",
        "hashtags": [],
    }

    result = validate_and_clean_script(copy.deepcopy(source), "quiz")

    assert "Tres... dos... uno" in result["full_script"]
    assert result["question"].startswith("¿")
    assert result["explanation"].startswith("¡")
    assert "#AprendeIngles" in result["hashtags"]
    assert result["video_description"].endswith("Sígueme para más tips de inglés 🦊")

    already_spanish = copy.deepcopy(source)
    already_spanish["full_script"] = "Piensa. TRES... DOS... UNO... elige four."
    preserved = validate_and_clean_script(already_spanish, "quiz")
    assert "TRES... DOS... UNO" in preserved["full_script"]


def test_shared_quiz_retry_preserves_existing_spanish_instruction(monkeypatch):
    calls = []
    first = representative("quiz")
    first["options"] = {"A": "same", "B": "same", "C": "same", "D": "same"}
    responses = iter((first, representative("quiz")))

    def create(**kwargs):
        calls.append(kwargs)
        payload = next(responses)
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    from script_generator import generate_script_from_prompt

    result = generate_script_from_prompt(
        "travel", {"id": "airport"}, "quiz", prompt="base prompt",
        system_instruction="existing Spanish system", client=client,
    )

    assert result["correct"] == "B"
    assert calls[1]["messages"] == [{
        "role": "user",
        "content": (
            "base prompt\n\nIMPORTANTE: Las 4 opciones A, B, C, D de CADA "
            "pregunta DEBEN ser palabras COMPLETAMENTE DIFERENTES. No repitas ninguna opción."
        ),
    }]
