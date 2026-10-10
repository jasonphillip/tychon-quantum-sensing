"""Package metadata must not grant a license the LICENSE file withholds."""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_pyproject_license_matches_proprietary_license_file():
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    license_text = (REPO / "LICENSE").read_text()
    assert "proprietary" in license_text.lower() and "No license is granted" in license_text
    assert project["license"] == "LicenseRef-Proprietary"
    assert project.get("license-files") == ["LICENSE"]
