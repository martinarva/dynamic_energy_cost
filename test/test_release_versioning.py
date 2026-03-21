"""Tests for release version alignment."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_release_version import normalize_tag, validate_release_version


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "dynamic_energy_cost" / "manifest.json"
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"


def test_manifest_version_is_plain_semver() -> None:
    """Manifest version stays in source control without a v prefix."""
    manifest = json.loads(MANIFEST_PATH.read_text())

    assert manifest["version"] == "0.9.6"
    assert not manifest["version"].startswith("v")


def test_normalize_tag_strips_optional_v_prefix() -> None:
    """Release tags normalize to the manifest version format."""
    assert normalize_tag("0.9.6") == "0.9.6"
    assert normalize_tag("v0.9.6") == "0.9.6"


def test_validate_release_version_accepts_matching_tag() -> None:
    """Release validation accepts matching versions."""
    assert validate_release_version(MANIFEST_PATH, "v0.9.6") == "0.9.6"


def test_release_workflow_validates_version_without_mutating_manifest() -> None:
    """Release workflow validates manifest version instead of rewriting it."""
    workflow = RELEASE_WORKFLOW_PATH.read_text()

    assert "check_release_version.py" in workflow
    assert "yq -i -o json" not in workflow
    assert "Adjust version number" not in workflow
