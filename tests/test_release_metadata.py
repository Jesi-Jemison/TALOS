"""TALOS v1.2.0 release metadata consistency checks."""
# TALOS FILE VERSION: v1.2.0

from pathlib import Path

from src import __version__


ROOT = Path(__file__).parent.parent


def test_source_version_readme_changelog_and_runtime_limits_are_in_sync():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    runtime_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    test_requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
    streamlit_config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

    assert __version__ == "1.2.0"
    assert f"Current release: v{__version__}" in readme
    assert f"## v{__version__}" in changelog
    assert f"TALOS v{__version__}" in app
    assert f"TALOS FILE VERSION: v{__version__}" in runtime_requirements
    assert f"TALOS FILE VERSION: v{__version__}" in test_requirements
    assert f"TALOS FILE VERSION: v{__version__}" in streamlit_config
    assert "maxUploadSize = 200" in streamlit_config
    assert '"csv", "xlsx", "xlsm", "xls"' in app


def test_excel_readers_and_chart_dependency_are_declared():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "altair>=5,<6" in requirements
    assert "openpyxl>=3.1,<4" in requirements
    assert "xlrd>=2,<3" in requirements


def test_version_comments_use_format_safe_text_and_asset_metadata():
    audit = (ROOT / "docs/version_comment_audit_v1.2.0.md").read_text(encoding="utf-8")
    demo_csv = (ROOT / "data/sample/talos_demo.csv").read_text(encoding="utf-8")
    demo_marker = (ROOT / "data/sample/talos_demo.csv.version").read_text(encoding="utf-8")
    emblem = (ROOT / "assets/talos-emblem.svg").read_text(encoding="utf-8")
    guardian = (ROOT / "assets/talos-sentinel-panel.webp").read_bytes()

    assert demo_csv.startswith("deity_name,deity_class,")
    assert "TALOS FILE VERSION: v1.2.0" in demo_marker
    assert "TALOS FILE VERSION: v1.2.0" in emblem
    assert b'talos:fileVersion="v1.2.0"' in guardian
    assert "LICENSE" in audit and "verbatim" in audit
    assert "assets/screenshots/talos-landing-20260925.jpg" in audit
    assert "pixels were compared before/after and are identical" in audit
