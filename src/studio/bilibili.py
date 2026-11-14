"""Native Simplified-Chinese author for the Bilibili editorial workspace."""

from __future__ import annotations

import copy
import json
from typing import Callable

from .creation import AuthorResult
from .editorial_costs import invoke_with_costs
from .models import CreationMode, Market


SYSTEM_INSTRUCTION = (
    "你是一位严谨、自然、善于观察的中英双语英语老师。"
    "你为 Bilibili 学习者创作内容，讲解和元数据使用自然简体中文，"
    "教学示例使用真实英语。只返回有效 JSON。"
)

_TYPE_REQUIREMENTS = {
    "educational": (
        "字段：hook、full_script、english_phrases、translations、tip、cta。"
        "translations 的值填写简体中文。"
    ),
    "quiz": (
        "字段：question、options（A/B/C/D 四个不同选项）、correct、explanation、"
        "questions、full_script、translations。思考倒计时使用“三、二、一”。"
    ),
    "true_false": (
        "字段：statement、correct（JSON 布尔值）、explanation、statements、"
        "full_script、translations。思考倒计时使用“三、二、一”。"
    ),
    "fill_blank": (
        "字段：sentence（必须含 ___）、blank_position、options（四项）、correct、"
        "explanation、translation、sentences、full_script。translation 使用简体中文。"
    ),
    "pronunciation": (
        "字段：word、phonetic、common_mistake、tip、full_script、translation。"
        "用中文解释英语发音，音标提示须便于普通话学习者理解。"
    ),
    "vocabulary": (
        "字段：title、difficulty、pairs（6-10 项）、full_script、translations、"
        "english_phrases。pairs 中保留兼容键 spanish，但它的值必须填写简体中文，"
        "english 的值填写英语。"
    ),
}


def _random_topic(*, allowed_categories):
    from script_generator import get_random_topic

    return get_random_topic(allowed_categories=allowed_categories)


def _find_topic(category, topic):
    from script_generator import find_topic

    return find_topic(category, topic)


def _topic_name(topic):
    from script_generator import get_topic_name

    return get_topic_name(topic)


def _generate(**kwargs):
    from script_generator import ZH_HANS_CLEANUP_POLICY, generate_script_from_prompt

    return generate_script_from_prompt(
        **kwargs,
        cleanup_policy=ZH_HANS_CLEANUP_POLICY,
        duplicate_options_instruction=(
            "A、B、C、D 四个选项必须完全不同，不得重复。"
        ),
    )


def _tracker():
    from cost_tracker import get_tracker

    return get_tracker()


class BilibiliScriptAuthor:
    """Create native zh-Hans/English scripts through shared generator seams."""

    def __init__(
        self,
        *,
        random_topic: Callable = _random_topic,
        topic_finder: Callable = _find_topic,
        topic_name: Callable = _topic_name,
        generator: Callable = _generate,
        tracker_getter: Callable = _tracker,
    ):
        self._random_topic = random_topic
        self._topic_finder = topic_finder
        self._topic_name = topic_name
        self._generator = generator
        self._tracker_getter = tracker_getter

    def generate(self, request, profile: dict) -> AuthorResult:
        self._validate_identities(request, profile)
        audience = copy.deepcopy(profile["audience"])
        video_type = (
            request.video_type
            or audience.get("content", {}).get("default_type")
            or "educational"
        )
        if video_type not in _TYPE_REQUIREMENTS:
            raise ValueError(f"unsupported video_type: {video_type}")

        if request.mode is CreationMode.DIRECTED:
            if not request.category:
                raise ValueError("directed creation requires category")
            category = request.category
            selected = self._topic_finder(category, request.topic or request.idea)
        else:
            category, selected = self._random_topic(
                allowed_categories=copy.deepcopy(
                    audience.get("content", {}).get("categories")
                )
            )

        prompt = self._build_prompt(
            request,
            profile,
            category,
            self._topic_name(copy.deepcopy(selected)),
            video_type,
        )
        tracker = self._tracker_getter()
        script, costs = invoke_with_costs(
            tracker,
            lambda: self._generator(
                category=category,
                topic=copy.deepcopy(selected),
                video_type=video_type,
                prompt=prompt,
                system_instruction=SYSTEM_INSTRUCTION,
            ),
        )
        return AuthorResult(script=copy.deepcopy(script), costs=costs)

    @staticmethod
    def _validate_identities(request, profile: dict) -> None:
        if request.market is not Market.BILIBILI:
            raise ValueError("BilibiliScriptAuthor supports only bilibili + zh-Hans + en")
        expected = {
            "profile_schema_version": 1,
            "workspace.profile_schema_version": 1,
            "workspace.workspace_id": "bilibili_zh_hans_en",
            "workspace.market": request.market.value,
            "workspace.native_language": request.native_language.value,
            "workspace.learning_language": request.learning_language.value,
            "audience.profile_schema_version": 1,
            "audience.audience": request.audience.value,
            "audience.name": request.audience.value,
            "voice.profile_schema_version": 1,
            "voice.workspace_id": "bilibili_zh_hans_en",
            "voice.audience": request.audience.value,
            "voice.locale": "zh-Hans",
        }
        for path, wanted in expected.items():
            value = profile
            try:
                for part in path.split("."):
                    value = value[part]
            except (KeyError, TypeError):
                value = None
            if value != wanted:
                raise ValueError(f"{path} mismatch")

    @staticmethod
    def _build_prompt(request, profile, category, topic_name, video_type) -> str:
        brief = request.model_dump(mode="json")
        policy = {
            "workspace": {
                key: copy.deepcopy(profile["workspace"].get(key))
                for key in (
                    "workspace_id", "market", "native_language",
                    "learning_language", "editorial", "metadata", "subtitles",
                )
            },
            "audience": {
                key: copy.deepcopy(profile["audience"].get(key))
                for key in (
                    "audience", "name", "content", "editorial", "metadata",
                )
            },
            "voice": {
                key: copy.deepcopy(profile["voice"].get(key))
                for key in ("workspace_id", "audience", "locale", "traits")
            },
        }
        return (
            "为 Bilibili 创作一条教授英语的课程脚本。\n"
            "讲解、旁白、标题、简介和互动文字必须使用自然简体中文；英语例句保留英语。\n"
            "内容要像亲近、准确、善于观察的老师，不使用空泛激励、虚假爆款承诺或生硬套话。\n"
            "从学习目标和主题重新创作，不照搬其他市场文案；保留学习目标而非原句。\n"
            "例子要符合中文学习者的真实语境，并在钩子、讲解结构、例句、互动和结尾之间做有目的的变化。\n"
            "输出须适合 zh-Hans/English 双语字幕。儿童内容必须安全、清晰、有节制地鼓励，"
            "不得夸张或幼稚化；成人内容保持自然直接。\n"
            "元数据适合 Bilibili，使用 5-7 个受众相关标签，不使用其他市场的标签回退。\n"
            f"视频类型：{video_type}\n类型契约：{_TYPE_REQUIREMENTS[video_type]}\n"
            f"选定分类：{category}\n选定主题：{topic_name}\n"
            f"创作请求：{json.dumps(brief, ensure_ascii=False, sort_keys=True)}\n"
            f"已解析配置：{json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
            "所有类型都必须包含 type、video_title、video_description、full_script、hashtags。"
            "只返回一个 JSON 对象。"
        )
