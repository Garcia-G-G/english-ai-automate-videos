import pytest


def test_presentation_policy_is_strict_and_localized():
    from pydantic import ValidationError
    from studio.renderer_presentation import RendererPresentation, resolve_presentation

    spanish = resolve_presentation("es")
    chinese = resolve_presentation("zh-Hans")
    assert spanish.question_number.format(number=2) == "Pregunta 2"
    assert spanish.thinking == "¡Piensa bien!"
    assert (spanish.true_label, spanish.false_label) == ("VERDADERO", "FALSO")
    assert (spanish.native_heading, spanish.learning_heading) == ("ESPAÑOL", "INGLÉS")
    assert chinese.question_number.format(number=2) == "问题 2"
    assert chinese.thinking == "仔细想想！"
    assert chinese.answer.format(answer="B") == "答案：B"
    assert (chinese.true_label, chinese.false_label) == ("正确", "错误")
    assert (chinese.native_heading, chinese.learning_heading) == ("中文", "英语")
    assert (chinese.educational_adults, chinese.educational_children) == (
        "英语微课堂", "少儿英语小课堂"
    )
    assert (chinese.native_field, chinese.learning_field) == ("spanish", "english")
    with pytest.raises(ValueError, match="native language"):
        resolve_presentation("fr")
    with pytest.raises(ValidationError):
        RendererPresentation(**{**chinese.model_dump(), "unexpected": True})


def test_gateway_renderers_receive_workspace_native_language(tmp_path):
    from tests.studio.test_legacy_pipeline import artifact, bundle, gateway_fakes

    (tmp_path / "art_01").mkdir()
    gateway, calls, _ = gateway_fakes(tmp_path)
    gateway.produce(artifact(), {"type": "educational", "full_script": "hola"},
                    bundle(), lambda *args: None)
    render = next(call for call in calls if call[0] == "render")
    assert render[-1]["native_language"] == "es"


def test_zh_hans_policy_reaches_actual_quiz_draw_calls(monkeypatch):
    import video.quiz as quiz
    from studio.renderer_presentation import resolve_presentation

    drawn = []
    monkeypatch.setattr(quiz, "draw_text_solid",
                        lambda draw, text, *args, **kwargs: drawn.append(text))
    data = {
        "question": "哪个词表示你好？", "question_number": "2",
        "options": {"A": "bye", "B": "hello", "C": "red", "D": "cat"},
        "correct": "B", "explanation": "Hello 表示你好。",
        "segment_times": {
            "option_a": {"start": 0.1}, "option_b": {"start": 0.2},
            "option_c": {"start": 0.3}, "option_d": {"start": 0.4},
            "think": {"start": 2.0}, "countdown_3": {"start": 4.0},
            "answer": {"start": 6.0}, "explanation": {"start": 9.0},
        },
    }
    policy = resolve_presentation("zh-Hans")
    quiz.create_frame_quiz(2.5, data, 10.0, presentation=policy)
    quiz.create_frame_quiz(6.5, data, 10.0, presentation=policy)
    assert "问题 2" in drawn
    assert "仔细想想！" in drawn
    assert "答案：B" in drawn
    assert not {"Pregunta 2", "¡Piensa bien!", "Respuesta: B"} & set(drawn)


def test_zh_hans_policy_reaches_true_false_and_vocabulary_draw_calls(monkeypatch):
    import video.true_false as true_false
    import video.vocabulary as vocabulary
    from studio.renderer_presentation import resolve_presentation

    policy = resolve_presentation("zh-Hans")
    buttons = []
    monkeypatch.setattr(
        true_false, "_draw_button",
        lambda frame, draw, label, *args, **kwargs: buttons.append(label),
    )
    true_false.create_frame_true_false(
        3.0,
        {"statement": "Hello 表示你好。", "correct": True,
         "explanation": "这是正确的。", "segment_times": {
             "options": {"start": 0.1}, "think": {"start": 0.5},
             "answer": {"start": 2.0}, "explanation": {"start": 5.0},
         }},
        6.0, presentation=policy,
    )
    assert any("正确" in label for label in buttons)
    assert any("错误" in label for label in buttons)
    assert not any("VERDADERO" in label or "FALSO" in label for label in buttons)

    drawn = []
    monkeypatch.setattr(vocabulary, "draw_text_solid",
                        lambda draw, text, *args, **kwargs: drawn.append(text))
    vocabulary.create_frame_vocabulary(
        1.0,
        {"title": "今日词汇", "pairs": [{"spanish": "你好", "english": "hello"}],
         "segment_times": {"title": {"start": 0.0, "end": 0.4},
                           "pair_0": {"start": 0.5, "end": 2.0}}},
        3.0, presentation=policy,
    )
    assert {"中文", "英语", "你好", "hello"} <= set(drawn)
    assert not {"ESPAÑOL", "INGLÉS"} & set(drawn)
