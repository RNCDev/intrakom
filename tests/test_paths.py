import sys
from pathlib import Path

from intrakom import paths


def test_config_dir_is_intrakom_under_home():
    assert paths.config_dir() == Path.home() / ".intrakom"


def test_lock_dir_under_config_dir():
    assert paths.lock_dir() == Path.home() / ".intrakom" / "locks"


def test_log_dir_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.log_dir("receiver") == Path.home() / "Library" / "Logs" / "Intrakom"


def test_log_dir_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.log_dir("receiver") == Path.home() / ".intrakom" / "logs"


def test_log_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.log_dir("receiver") == tmp_path / "Intrakom" / "Logs"
