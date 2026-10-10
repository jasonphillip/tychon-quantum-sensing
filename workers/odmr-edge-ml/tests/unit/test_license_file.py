"""The repository LICENSE is Apache-2.0 (decided 2026-10-10)."""

from pathlib import Path


def test_license_file_is_apache_2():
    text = (Path(__file__).resolve().parents[2] / "LICENSE").read_text()
    assert "Apache License" in text and "Version 2.0, January 2004" in text
    assert "All rights reserved" not in text
