from __future__ import annotations

from pathlib import Path

from conftest import create_db
from workbuddy_migrator.doctor import run_doctor
from workbuddy_migrator.paths import detect_paths


def test_detect_paths_uses_workbuddy_home_env(workbuddy_home: Path) -> None:
    paths = detect_paths()
    assert paths.root == workbuddy_home
    assert paths.db == workbuddy_home / "workbuddy.db"
    assert paths.projects == workbuddy_home / "projects"


def test_doctor_reports_missing_db(workbuddy_home: Path) -> None:
    result = run_doctor(detect_paths())
    assert result["ok"] is False
    assert "workbuddy.db is missing" in result["errors"]


def test_doctor_passes_fixture_schema(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    result = run_doctor(detect_paths())
    assert result["ok"] is True
    assert result["schema"]["has_sessions"] is True
    assert result["schema"]["has_automation_owner"] is True
