import logging
from pathlib import Path

from intrakom import logging_setup, paths


def test_configure_logging_creates_log_file(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "log_dir", lambda c: tmp_path)
    monkeypatch.setattr(logging_setup, "_configured", False)
    logging_setup.configure_logging("receiver")
    log = logging.getLogger("intrakom.test")
    log.info("hello from test")
    for h in logging.getLogger().handlers:
        h.flush()
    contents = (tmp_path / "receiver.log").read_text()
    assert "hello from test" in contents


def test_debug_env_sets_debug_level(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "log_dir", lambda c: tmp_path)
    monkeypatch.setattr(logging_setup, "_configured", False)
    monkeypatch.setenv("INTRAKOM_DEBUG", "1")
    logging_setup.configure_logging("receiver")
    assert logging.getLogger().level == logging.DEBUG
