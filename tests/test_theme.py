"""Tests for TALOS's compact, session-independent theme token system."""

from pathlib import Path

import pytest

from src.theme import (
    DEFAULT_THEME,
    THEME_TOKENS,
    normalize_theme_name,
    theme_token_css,
    theme_tokens,
)


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return sum(weight * channel for weight, channel in zip((0.2126, 0.7152, 0.0722), linear))


def _contrast(first: str, second: str) -> float:
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_dark_is_default_and_themes_share_one_complete_token_shape():
    assert DEFAULT_THEME == "Dark"
    assert set(THEME_TOKENS) == {"Dark", "Light"}
    assert set(THEME_TOKENS["Dark"]) == set(THEME_TOKENS["Light"])
    assert normalize_theme_name(" light ") == "Light"
    assert "--talos-bg" in theme_token_css("Dark")
    assert "--text-color: var(--talos-text)" in theme_token_css("Light")
    assert "color-scheme: light" in theme_token_css("Light")
    assert 'body, [data-testid="stAppViewContainer"], .stApp' in theme_token_css("Light")


def test_body_and_muted_text_meet_readable_contrast_in_both_themes():
    for name in THEME_TOKENS:
        tokens = theme_tokens(name)
        assert _contrast(tokens["talos-text"], tokens["talos-bg"]) >= 7
        assert _contrast(tokens["talos-muted"], tokens["talos-panel"]) >= 4.5


def test_alert_surfaces_keep_readable_text_and_component_overrides():
    stylesheet = (Path(__file__).parent.parent / "assets" / "talos.css").read_text(
        encoding="utf-8"
    )
    for name in THEME_TOKENS:
        tokens = theme_tokens(name)
        assert _contrast(tokens["talos-alert-text"], tokens["talos-alert-bg"]) >= 7
        assert "--talos-alert-bg" in theme_token_css(name)
    assert '[data-testid="stAlert"] [data-testid="stMarkdownContainer"] *' in stylesheet
    assert '[data-testid="stExpander"] details > summary:focus-visible' in stylesheet
    assert '[data-testid="stDataFrame"] [data-testid="stToolbar"]' in stylesheet
    assert "color: var(--talos-alert-text) !important" in stylesheet
    assert "[data-testid=\"stWidgetLabel\"] p" in stylesheet
    assert "background-color: var(--talos-input) !important" in stylesheet
    assert "background-color: var(--talos-panel) !important" in stylesheet
    assert '[data-testid="stSelectbox"] [role="group"]' in stylesheet
    assert '[data-testid="stSelectbox"] input[role="combobox"]' in stylesheet
    assert ".talos-section-divider::after" in stylesheet


def test_theme_tokens_are_copied_and_invalid_names_are_rejected():
    copied = theme_tokens("Dark")
    copied["talos-bg"] = "#FFFFFF"
    assert theme_tokens("Dark")["talos-bg"] == "#09080C"

    with pytest.raises(ValueError, match="Unsupported TALOS theme"):
        normalize_theme_name("Sepia")
