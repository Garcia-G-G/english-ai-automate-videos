import json
import os
import stat
from datetime import datetime, timezone

import pytest

from studio.artifacts import (
    ArtifactAlreadyExists,
    ArtifactCorrupt,
    ArtifactNotFound,
    ArtifactRepository,
    ArtifactRepositoryError,
    ArtifactWriteError,
    InvalidArtifactId,
)
from studio.models import CreationRequest, VideoArtifact


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def make_artifact(artifact_id="art_01", *, chinese=False):
    request = CreationRequest(
        market="bilibili" if chinese else "youtube",
        native_language="zh-Hans" if chinese else "es",
        learning_language="en",
        audience="adults",
        mode="auto",
        idea="颜色练习" if chinese else "actually",
        notes="自然中文讲解" if chinese else None,
    )
    return VideoArtifact.new(request, artifact_id, NOW)


def canonical_path(root, artifact_id="art_01"):
    return root / artifact_id / "artifact.json"


def write_payload(root, artifact_id, payload):
    directory = root / artifact_id
    directory.mkdir(parents=True)
    path = directory / "artifact.json"
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
    return path


INVALID_IDS = [
    "",
    ".",
    "..",
    "../escape",
    "a/b",
    "a\\b",
    " space ",
    ".hidden",
    "-leading",
    "a b",
    "á",
    "a" * 129,
]


@pytest.mark.parametrize("artifact_id", INVALID_IDS)
def test_artifact_dir_rejects_invalid_ids_without_side_effect(tmp_path, artifact_id):
    root = tmp_path / "artifacts"
    repo = ArtifactRepository(root)

    with pytest.raises(InvalidArtifactId, match="artifact"):
        repo.artifact_dir(artifact_id)

    assert not root.exists()


@pytest.mark.parametrize("artifact_id", INVALID_IDS)
@pytest.mark.parametrize("operation", ["create", "save", "load"])
def test_artifact_operations_reject_invalid_ids(tmp_path, artifact_id, operation):
    repo = ArtifactRepository(tmp_path)

    with pytest.raises(InvalidArtifactId, match="artifact"):
        if operation == "load":
            repo.load(artifact_id)
        else:
            getattr(repo, operation)(make_artifact(artifact_id))


def test_artifact_dir_only_calculates_canonical_directory(tmp_path):
    root = tmp_path / "artifacts"
    repo = ArtifactRepository(root)

    assert repo.artifact_dir("art_01") == root / "art_01"
    assert not root.exists()


def test_create_writes_utf8_final_newline_and_round_trips(tmp_path):
    repo = ArtifactRepository(tmp_path)
    artifact = make_artifact("bili_01", chinese=True)

    repo.create(artifact)

    path = canonical_path(tmp_path, "bili_01")
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert "颜色练习" in raw.decode("utf-8")
    assert repo.load("bili_01") == artifact


def test_create_atomically_claims_identity_without_overwriting(tmp_path):
    claimed = tmp_path / "art_01"
    claimed.mkdir()
    marker = claimed / "owner.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ArtifactAlreadyExists, match="art_01"):
        ArtifactRepository(tmp_path).create(make_artifact())

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not canonical_path(tmp_path).exists()


def test_save_updates_existing_artifact_and_does_not_append_events(tmp_path):
    repo = ArtifactRepository(tmp_path)
    artifact = make_artifact()
    repo.create(artifact)
    changed = artifact.model_copy(update={"error": "visible"})

    repo.save(changed)

    loaded = repo.load("art_01")
    assert loaded == changed
    assert loaded.events == artifact.events


def test_save_never_creates_missing_artifact(tmp_path):
    repo = ArtifactRepository(tmp_path)

    with pytest.raises(ArtifactNotFound, match="art_01"):
        repo.save(make_artifact())

    assert not canonical_path(tmp_path).exists()


def test_successful_create_and_save_leave_no_temporary_sibling(tmp_path):
    repo = ArtifactRepository(tmp_path)
    artifact = make_artifact()
    repo.create(artifact)
    repo.save(artifact.model_copy(update={"error": "saved"}))

    assert [path.name for path in (tmp_path / "art_01").iterdir()] == [
        "artifact.json"
    ]


def test_failed_save_preserves_canonical_and_removes_owned_temp(tmp_path, monkeypatch):
    repo = ArtifactRepository(tmp_path)
    artifact = make_artifact()
    repo.create(artifact)
    path = canonical_path(tmp_path)
    before = path.read_bytes()
    failure = OSError("replace unavailable")

    def fail_replace(source, destination):
        raise failure

    monkeypatch.setattr("studio.artifacts.os.replace", fail_replace)

    with pytest.raises(ArtifactWriteError, match="art_01") as caught:
        repo.save(artifact.model_copy(update={"error": "new value"}))

    assert caught.value.__cause__ is failure
    assert path.read_bytes() == before
    assert [entry.name for entry in path.parent.iterdir()] == ["artifact.json"]


def test_failed_create_removes_its_empty_claimed_directory(tmp_path, monkeypatch):
    repo = ArtifactRepository(tmp_path)

    def fail_replace(source, destination):
        raise OSError("replace unavailable")

    monkeypatch.setattr("studio.artifacts.os.replace", fail_replace)

    with pytest.raises(ArtifactWriteError, match="art_01"):
        repo.create(make_artifact())

    assert not (tmp_path / "art_01").exists()


def test_atomic_write_fsyncs_file_and_artifact_directory(tmp_path, monkeypatch):
    seen = []
    real_fsync = os.fsync

    def recording_fsync(file_descriptor):
        seen.append(stat.S_ISDIR(os.fstat(file_descriptor).st_mode))
        return real_fsync(file_descriptor)

    monkeypatch.setattr("studio.artifacts.os.fsync", recording_fsync)

    ArtifactRepository(tmp_path).create(make_artifact())

    assert False in seen
    assert True in seen


@pytest.mark.parametrize("schema_version", [1, 3])
@pytest.mark.parametrize("operation", ["create", "save"])
def test_writes_reject_non_v2_artifacts(tmp_path, schema_version, operation):
    repo = ArtifactRepository(tmp_path)
    artifact = make_artifact()
    if operation == "save":
        repo.create(artifact)
    unsupported = artifact.model_copy(update={"schema_version": schema_version})

    with pytest.raises(ArtifactWriteError, match="schema_version.*2"):
        getattr(repo, operation)(unsupported)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("malformed", "{not json"),
        ("invalid_utf8", b"\xff\xfe"),
        ("schema_v1", None),
        ("schema_unknown", None),
        ("unknown_field", None),
        ("id_mismatch", None),
    ],
)
def test_load_rejects_corrupt_payloads_with_canonical_path(tmp_path, name, payload):
    artifact_id = name
    if payload is None:
        data = json.loads(make_artifact(artifact_id).model_dump_json())
        if name == "schema_v1":
            data["schema_version"] = 1
        elif name == "schema_unknown":
            data["schema_version"] = 3
        elif name == "unknown_field":
            data["unexpected"] = True
        elif name == "id_mismatch":
            data["artifact_id"] = "different_id"
        payload = json.dumps(data, ensure_ascii=False)
    path = write_payload(tmp_path, artifact_id, payload)

    with pytest.raises(ArtifactCorrupt, match=f"{artifact_id}.*artifact.json"):
        ArtifactRepository(tmp_path).load(artifact_id)

    assert path.exists()


def test_load_rejects_canonical_directory(tmp_path):
    path = canonical_path(tmp_path)
    path.mkdir(parents=True)

    with pytest.raises(ArtifactCorrupt, match="art_01.*artifact.json"):
        ArtifactRepository(tmp_path).load("art_01")


def test_load_and_save_reject_canonical_symlink(tmp_path):
    target = tmp_path / "target.json"
    target.write_text(make_artifact().model_dump_json(), encoding="utf-8")
    path = canonical_path(tmp_path)
    path.parent.mkdir()
    try:
        path.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unsupported: {exc}")
    repo = ArtifactRepository(tmp_path)

    with pytest.raises(ArtifactCorrupt, match="art_01.*artifact.json"):
        repo.load("art_01")
    with pytest.raises(ArtifactCorrupt, match="art_01.*artifact.json"):
        repo.save(make_artifact())


@pytest.mark.parametrize("operation", ["load", "save"])
def test_direct_missing_canonical_is_not_found(tmp_path, operation):
    repo = ArtifactRepository(tmp_path)

    with pytest.raises(ArtifactNotFound, match="art_01.*artifact.json"):
        if operation == "load":
            repo.load("art_01")
        else:
            repo.save(make_artifact())


def test_listing_incomplete_child_is_corrupt(tmp_path):
    root = tmp_path / "artifacts"
    incomplete = root / "incomplete"
    incomplete.mkdir(parents=True)

    with pytest.raises(ArtifactCorrupt, match="incomplete.*artifact.json"):
        ArtifactRepository(root).list_artifacts()


def test_listing_missing_root_is_empty(tmp_path):
    assert ArtifactRepository(tmp_path / "missing").list_artifacts() == []


def test_listing_is_ordered_by_artifact_id_and_ignores_root_files(tmp_path):
    root = tmp_path / "artifacts"
    repo = ArtifactRepository(root)
    repo.create(make_artifact("z_last"))
    repo.create(make_artifact("a_first"))
    (root / "README.txt").write_text("ignore", encoding="utf-8")

    assert [artifact.artifact_id for artifact in repo.list_artifacts()] == [
        "a_first",
        "z_last",
    ]


def test_listing_rejects_symlinked_artifact_child(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    target = tmp_path / "real"
    target.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlink creation unsupported: {exc}")

    with pytest.raises(ArtifactCorrupt, match="linked"):
        ArtifactRepository(root).list_artifacts()


def test_repository_errors_share_typed_base():
    assert issubclass(InvalidArtifactId, ArtifactRepositoryError)
    assert issubclass(ArtifactAlreadyExists, ArtifactRepositoryError)
    assert issubclass(ArtifactNotFound, ArtifactRepositoryError)
    assert issubclass(ArtifactCorrupt, ArtifactRepositoryError)
    assert issubclass(ArtifactWriteError, ArtifactRepositoryError)
