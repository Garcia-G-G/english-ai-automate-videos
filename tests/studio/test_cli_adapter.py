import ast
import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _artifact(artifact_id="safe_name", state="ready_for_review"):
    return SimpleNamespace(
        artifact_id=artifact_id,
        state=SimpleNamespace(value=state),
        paths=SimpleNamespace(video="video/final.mp4"),
        error=None,
    )


def test_cli_source_has_no_low_level_creation_calls_or_imports():
    tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    forbidden = {"generate_tts", "merge_script_into_tts", "render_video", "generate_script"}
    calls = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imports = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert not forbidden & calls
    assert not forbidden & imports


@pytest.mark.parametrize(
    ("workspace", "audience", "native"),
    [("youtube", "adults", "es"), ("youtube", "children", "es"),
     ("bilibili", "adults", "zh-Hans"), ("bilibili", "children", "zh-Hans")],
)
def test_run_creation_constructs_typed_workspace_request(monkeypatch, tmp_path,
                                                          workspace, audience, native):
    import main
    captured = {}

    class Service:
        def create(self, request, **kwargs):
            captured["request"] = copy.deepcopy(request)
            captured["kwargs"] = kwargs
            return _artifact(kwargs.get("artifact_id") or "generated")

    monkeypatch.setattr(main, "get_creation_service", lambda **kwargs: Service())
    artifact, video = main.run_creation(
        workspace=workspace, audience=audience, idea="lesson", mode="auto",
        root=tmp_path, artifact_id="safe_name",
    )
    expected = {
        "market": workspace, "native_language": native,
        "learning_language": "en", "audience": audience,
    }
    assert expected.items() <= captured["request"].model_dump(mode="json").items()
    assert artifact.artifact_id == "safe_name"
    assert video == tmp_path / "safe_name/video/final.mp4"


def test_provided_script_uses_typed_author_and_preserves_input(monkeypatch, tmp_path):
    import main
    seen = {}

    def build(**kwargs):
        seen.update(kwargs)
        class Service:
            def create(self, request, **create_kwargs):
                author = kwargs["youtube_author"]
                seen["outcome"] = author.generate(request, {})
                return _artifact("provided")
        return Service()

    monkeypatch.setattr(main, "get_creation_service", build)
    script = {"type": "educational", "full_script": "¡Hola! hello", "nested": ["safe"]}
    original = copy.deepcopy(script)
    main.run_creation(workspace="youtube", audience="adults", idea="provided",
                      mode="directed", root=tmp_path, supplied_script=script)
    assert seen["outcome"].script == script
    assert script == original


def test_kids_alias_warns_and_dry_run_never_builds_service(monkeypatch, capsys):
    import main
    monkeypatch.setattr(main, "get_creation_service",
                        lambda **kwargs: pytest.fail("service must not be built"))
    monkeypatch.setattr(sys, "argv", ["main.py", "--random", "--profile", "kids", "--dry-run"])
    main.main()
    output = capsys.readouterr().out
    assert "deprecated" in output.lower()
    assert "children" in output
    assert "dry run" in output.lower()


def test_upload_is_refused_before_uploader_for_review_artifact(monkeypatch, tmp_path, capsys):
    import main
    monkeypatch.setattr(main, "get_creation_service", lambda **kwargs: SimpleNamespace(
        create=lambda *args, **kwargs: _artifact("review")
    ))
    monkeypatch.setattr(main, "upload_video",
                        lambda *args, **kwargs: pytest.fail("upload must not run"))
    main.run_creation(workspace="youtube", audience="adults", idea="lesson",
                      mode="auto", root=tmp_path, upload=True)
    assert "owner approval" in capsys.readouterr().out.lower()


def test_list_only_cli_does_not_construct_service(monkeypatch):
    import main
    monkeypatch.setattr(main, "get_creation_service",
                        lambda **kwargs: pytest.fail("list must not build service"))
    monkeypatch.setattr(main, "list_scripts", lambda: None)
    monkeypatch.setattr(sys, "argv", ["main.py", "--list-scripts"])
    main.main()
