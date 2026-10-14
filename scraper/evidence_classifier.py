from __future__ import annotations

from .evidence_engine import analyze_text
from .models import Classification


def classify(text: str) -> Classification:
    """Backward-compatible entry point for the shared evidence engine."""
    return analyze_text(text)
