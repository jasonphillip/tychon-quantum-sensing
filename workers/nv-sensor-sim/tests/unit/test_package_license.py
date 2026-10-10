"""Package metadata and the LICENSE file must state the same license (Apache-2.0, decided 2026-10-10)."""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_pyproject_license_matches_license_file():
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    license_text = (REPO / "LICENSE").read_text()
    assert "Apache License" in license_text and "Version 2.0, January 2004" in license_text
    assert "All rights reserved" not in license_text
    assert project["license"] == "Apache-2.0"
    assert project.get("license-files") == ["LICENSE"]
