"""Small, testable colour-token definitions for the TALOS interface."""

from __future__ import annotations

from typing import Any


DEFAULT_THEME = "Dark"

THEME_TOKENS: dict[str, dict[str, str]] = {
    "Dark": {
        "color-scheme": "dark",
        "talos-bg": "#09080C",
        "talos-panel": "#111017",
        "talos-panel-raised": "#191720",
        "talos-line": "rgba(195, 154, 90, 0.34)",
        "talos-bronze": "#C39A5A",
        "talos-bronze-strong": "#E1BF78",
        "talos-violet": "#7254B5",
        "talos-lilac": "#BDA8F2",
        "talos-text": "#E8DEFF",
        "talos-muted": "#C4BED0",
        "talos-input": "#15131B",
        "talos-soft": "#17141D",
        "talos-highlight": "rgba(114, 84, 181, 0.20)",
        "talos-hero-start": "#191720",
        "talos-hero-end": "#111017",
        "talos-score-surface": "#211B26",
    },
    "Light": {
        "color-scheme": "light",
        "talos-bg": "#F3EEE4",
        "talos-panel": "#FBF8F1",
        "talos-panel-raised": "#E8E0D1",
        "talos-line": "#B7A98F",
        "talos-bronze": "#896337",
        "talos-bronze-strong": "#6D4A28",
        "talos-violet": "#67508C",
        "talos-lilac": "#49365A",
        "talos-text": "#322417",
        "talos-muted": "#534638",
        "talos-input": "#FFFFFF",
        "talos-soft": "#F6F1E8",
        "talos-highlight": "#EEE6D9",
        "talos-hero-start": "#E8E0D1",
        "talos-hero-end": "#F3EEE4",
        "talos-score-surface": "#EFE7DA",
    },
}


def normalize_theme_name(theme: str) -> str:
    """Return a supported display name or raise for an invalid preference."""
    normalized = str(theme).strip().title()
    if normalized not in THEME_TOKENS:
        raise ValueError(f"Unsupported TALOS theme: {theme!r}.")
    return normalized


def theme_token_css(theme: str) -> str:
    """Build root CSS variables for a theme without changing analysis state."""
    name = normalize_theme_name(theme)
    tokens = THEME_TOKENS[name]
    declarations = [f"color-scheme: {tokens['color-scheme']};"]
    declarations.extend(
        f"--{key}: {value};"
        for key, value in tokens.items()
        if key != "color-scheme"
    )
    return ":root {\n    " + "\n    ".join(declarations) + "\n}"


def theme_tokens(theme: str) -> dict[str, str]:
    """Return a copy of one theme's token mapping for rendering and checks."""
    return THEME_TOKENS[normalize_theme_name(theme)].copy()
