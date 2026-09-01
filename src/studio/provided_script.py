"""Request-scoped author for owner-supplied script content."""

from __future__ import annotations

import copy

from .creation import AuthorResult


class ProvidedScriptAuthor:
    def __init__(self, script: dict):
        if type(script) is not dict:
            raise TypeError("supplied script must be dict")
        self._script = copy.deepcopy(script)

    def generate(self, request, profile) -> AuthorResult:
        return AuthorResult(script=copy.deepcopy(self._script))
