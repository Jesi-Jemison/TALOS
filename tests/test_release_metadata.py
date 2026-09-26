"""TALOS v1.1.2 release metadata consistency checks."""

from pathlib import Path

from src import __version__


ROOT = Path(__file__).parent.parent


def test_source_version_readme_changelog_and_ui_footer_are_in_sync():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    runtime_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    test_requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")

    assert __version__ == "1.1.2"
    assert f"Current release: v{__version__}" in readme
    assert f"## v{__version__}" in changelog
    assert f"TALOS v{__version__}" in app
    assert f"# TALOS v{__version__}" in runtime_requirements
    assert f"# TALOS v{__version__}" in test_requirements
