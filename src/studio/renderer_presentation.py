"""Workspace-native, renderer-only presentation copy and field views."""

from pydantic import BaseModel, ConfigDict


class RendererPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    native_language: str
    question_number: str
    thinking: str
    answer: str
    true_label: str
    false_label: str
    native_heading: str
    learning_heading: str
    educational_adults: str
    educational_children: str
    pronunciation_prompt: str
    pronunciation_incorrect: str
    pronunciation_correct: str
    native_field: str = "spanish"
    learning_field: str = "english"


_POLICIES = {
    "es": RendererPresentation(
        native_language="es", question_number="Pregunta {number}",
        thinking="¡Piensa bien!", answer="Respuesta: {answer}",
        true_label="VERDADERO", false_label="FALSO",
        native_heading="ESPAÑOL", learning_heading="INGLÉS",
        educational_adults="MINI CLASE DE INGLÉS",
        educational_children="¡INGLÉS PARA PEQUES!",
        pronunciation_prompt="¿Cómo se pronuncia?",
        pronunciation_incorrect="Incorrecto:",
        pronunciation_correct="Correcto:",
    ),
    "zh-Hans": RendererPresentation(
        native_language="zh-Hans", question_number="问题 {number}",
        thinking="仔细想想！", answer="答案：{answer}",
        true_label="正确", false_label="错误",
        native_heading="中文", learning_heading="英语",
        educational_adults="英语微课堂",
        educational_children="少儿英语小课堂",
        pronunciation_prompt="怎么发音？",
        pronunciation_incorrect="错误：",
        pronunciation_correct="正确：",
    ),
}


def resolve_presentation(native_language: str) -> RendererPresentation:
    try:
        return _POLICIES[native_language].model_copy(deep=True)
    except KeyError as exc:
        raise ValueError(f"unsupported renderer native language: {native_language}") from exc
