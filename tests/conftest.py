"""Shared fixtures: the tests never write into the user's home."""

import pytest


@pytest.fixture(autouse=True)
def _recent_files_stay_in_tmp(tmp_path, monkeypatch):
    """The recent-documents list lives under ~/.noodler; not during a test."""
    import noodler.app as app

    monkeypatch.setattr(app, "RECENT_FILE", tmp_path / "recent.json")
