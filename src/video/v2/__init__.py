"""v2 render engine — design-token driven renderers (educational only, for now).

Usage: ``generate_video(..., engine_version="v2")`` or the ``--v2`` CLI flag.
v1 renderers are untouched; this package is fully additive.
"""

from .educational import EducationalRendererV2

__all__ = ["EducationalRendererV2"]
