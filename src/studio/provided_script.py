"""Request-scoped author for owner-supplied script content."""

from __future__ import annotations

import copy
import logging

from .creation import AuthorResult

logger = logging.getLogger(__name__)


class ProvidedScriptAuthor:
    def __init__(self, script: dict):
        if type(script) is not dict:
            raise TypeError("supplied script must be dict")
        self._script = copy.deepcopy(script)

    def generate(self, request, profile) -> AuthorResult:
        from script_schema import validate_script

        validate_script(
            copy.deepcopy(self._script),
            video_type=request.video_type,
            source="owner-supplied script",
        )

        # THE CLEANER RUNS ON OWNER-SUPPLIED SCRIPTS TOO.
        #
        # validate_and_clean_script finds the English spans quoted in
        # full_script and adds the ones missing from english_phrases. Every
        # GPT script has always gone through it; a queued script went through
        # validate_script alone, which only checks the shape.
        #
        # The cost of the gap is visible on screen: video/__init__.py builds
        # english_set by splitting the DECLARED phrases into words, and
        # colours each word by membership. So an English sentence whose words
        # are only partly declared gets painted in pieces -- the owner sent a
        # frame reading "Escribes sorry for being late" where "sorry for" is
        # yellow, "being" is Spanish grey and "late." is blue, because
        # "sorry" and "for" appear in another declared phrase and "being" and
        # "late" appear in none.
        # ONLY english_phrases IS TAKEN BACK. The cleaner also normalises
        # full_script and stamps warnings, and a supplied script must come out
        # the way the owner wrote it -- test_provided_script_..._preserves_input
        # says exactly that, and it is right. The narrow thing needed here is
        # the phrase list, because that is what the colouring reads.
        script = copy.deepcopy(self._script)
        try:
            from script_generator import validate_and_clean_script
            cleaned = validate_and_clean_script(copy.deepcopy(script),
                                                request.video_type)
            phrases = (cleaned or {}).get("english_phrases")
            if phrases and list(phrases) != list(script.get("english_phrases") or []):
                script["english_phrases"] = list(phrases)
        except Exception:                                   # noqa: BLE001
            # A cleaner that raises must not cost the owner a written script.
            logger.warning("could not clean the supplied script", exc_info=True)

        return AuthorResult(script=script)
