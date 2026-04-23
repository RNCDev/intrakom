import hashlib
import sys
import pytest

from intrakom import single_instance, paths


def test_first_acquire_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "lock_dir", lambda: tmp_path)
    handle = single_instance.acquire("Office")
    assert handle is not None


def test_second_acquire_same_name_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "lock_dir", lambda: tmp_path)
    first = single_instance.acquire("Office2")
    assert first is not None
    second = single_instance.acquire("Office2")
    assert second is None


def test_different_names_coexist(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "lock_dir", lambda: tmp_path)
    a = single_instance.acquire("A")
    b = single_instance.acquire("B")
    assert a is not None
    assert b is not None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only stale lock path")
def test_stale_lock_is_stolen(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "lock_dir", lambda: tmp_path)
    name = "StaleTest"
    digest = hashlib.sha1(name.encode()).hexdigest()
    stale = tmp_path / f"intrakom-receiver-{digest}.lock"
    stale.write_text("999999")  # not a live PID
    handle = single_instance.acquire(name)
    assert handle is not None
