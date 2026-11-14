"""Atomic persistence for canonical video artifacts."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import List

from .models import VideoArtifact


_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_CANONICAL_NAME = "artifact.json"


class ArtifactRepositoryError(Exception):
    """Base class for canonical artifact repository failures."""


class InvalidArtifactId(ArtifactRepositoryError):
    """An artifact ID is unsafe for use as a repository directory."""


class ArtifactAlreadyExists(ArtifactRepositoryError):
    """An artifact identity has already been claimed."""


class ArtifactNotFound(ArtifactRepositoryError):
    """A requested canonical artifact does not exist."""


class ArtifactCorrupt(ArtifactRepositoryError):
    """A canonical artifact entry is malformed or unsafe."""


class ArtifactWriteError(ArtifactRepositoryError):
    """A canonical artifact could not be durably written."""


class ArtifactRepository:
    """Store schema-version-2 artifacts below one dedicated root."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def artifact_dir(self, artifact_id: str) -> Path:
        self._validate_id(artifact_id)
        return self.root / artifact_id

    def create(self, artifact: VideoArtifact) -> None:
        self._validate_writable(artifact)
        artifact_id = artifact.artifact_id
        directory = self.artifact_dir(artifact_id)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            directory.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise ArtifactAlreadyExists(
                f"artifact {artifact_id!r} already exists at {directory}"
            ) from exc
        except OSError as exc:
            raise ArtifactWriteError(
                f"could not claim artifact {artifact_id!r} at {directory}"
            ) from exc

        try:
            self._atomic_write(artifact, directory)
        except ArtifactWriteError:
            if not (directory / _CANONICAL_NAME).exists():
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise

    def save(self, artifact: VideoArtifact) -> None:
        self._validate_writable(artifact)
        artifact_id = artifact.artifact_id
        directory = self.artifact_dir(artifact_id)
        self._require_canonical_file(artifact_id, directory)
        self._atomic_write(artifact, directory)

    def load(self, artifact_id: str) -> VideoArtifact:
        directory = self.artifact_dir(artifact_id)
        path = self._require_canonical_file(artifact_id, directory)
        try:
            payload = path.read_text(encoding="utf-8")
            artifact = VideoArtifact.model_validate_json(payload)
        except Exception as exc:
            raise ArtifactCorrupt(
                f"artifact {artifact_id!r} is corrupt at {path}"
            ) from exc

        if artifact.schema_version != 2:
            raise ArtifactCorrupt(
                f"artifact {artifact_id!r} at {path} has unsupported "
                f"schema_version {artifact.schema_version}; expected 2"
            )
        if artifact.artifact_id != artifact_id:
            raise ArtifactCorrupt(
                f"artifact ID mismatch at {path}: requested {artifact_id!r}, "
                f"payload has {artifact.artifact_id!r}"
            )
        return artifact

    def list_artifacts(self) -> List[VideoArtifact]:
        if not self.root.exists():
            return []
        if self.root.is_symlink() or not self.root.is_dir():
            raise ArtifactCorrupt(f"artifact repository root is invalid: {self.root}")

        artifacts = []
        for entry in sorted(self.root.iterdir(), key=lambda path: path.name):
            if entry.is_symlink():
                if entry.is_dir():
                    raise ArtifactCorrupt(
                        f"symlinked artifact directory is invalid: {entry}"
                    )
                continue
            if not entry.is_dir():
                continue
            try:
                self._validate_id(entry.name)
            except InvalidArtifactId as exc:
                raise ArtifactCorrupt(
                    f"invalid artifact child directory: {entry}"
                ) from exc
            try:
                artifacts.append(self.load(entry.name))
            except ArtifactNotFound as exc:
                raise ArtifactCorrupt(
                    f"incomplete artifact at {entry / _CANONICAL_NAME}"
                ) from exc
        return artifacts

    @staticmethod
    def _validate_id(artifact_id: str) -> None:
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
            raise InvalidArtifactId(f"invalid artifact ID: {artifact_id!r}")

    def _validate_writable(self, artifact: VideoArtifact) -> None:
        self._validate_id(artifact.artifact_id)
        if artifact.schema_version != 2:
            raise ArtifactWriteError(
                f"artifact {artifact.artifact_id!r} has schema_version "
                f"{artifact.schema_version}; expected 2"
            )

    @staticmethod
    def _require_canonical_file(artifact_id: str, directory: Path) -> Path:
        path = directory / _CANONICAL_NAME
        if path.is_symlink():
            raise ArtifactCorrupt(
                f"canonical artifact must not be a symlink: {path}"
            )
        if not path.exists():
            raise ArtifactNotFound(
                f"artifact {artifact_id!r} not found at {path}"
            )
        if not path.is_file():
            raise ArtifactCorrupt(
                f"canonical artifact is not a regular file: {path}"
            )
        return path

    @staticmethod
    def _atomic_write(artifact: VideoArtifact, directory: Path) -> None:
        artifact_id = artifact.artifact_id
        path = directory / _CANONICAL_NAME
        temporary = None
        descriptor = None
        try:
            serialized = artifact.model_dump_json(indent=2) + "\n"
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".artifact.json.",
                suffix=".tmp",
                dir=directory,
            )
            temporary = Path(temporary_name)
            stream = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
            descriptor = None
            with stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception as exc:
            raise ArtifactWriteError(
                f"could not write artifact {artifact_id!r} at {path}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
