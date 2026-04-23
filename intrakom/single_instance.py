"""
Single-instance enforcement for the receiver, keyed by --name.

POSIX: fcntl.flock() on ~/.intrakom/locks/intrakom-receiver-<sha1(name)>.lock.
Windows: named mutex Global\\intrakom-receiver-<sha1(name)>.

Returns an opaque handle on success, None on failure. The handle must be kept
alive for the life of the process (attach to a module-level global in main()).
Stale POSIX locks are detected by reading the PID from the lock file and
checking if that PID still exists — stale locks are stolen.
"""

import hashlib
import logging
import os
import sys
from typing import Any, Optional

from intrakom import paths

logger = logging.getLogger(__name__)


def _key(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"intrakom-receiver-{digest}"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _acquire_posix(name: str) -> Optional[Any]:
    import fcntl

    directory = paths.lock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / f"{_key(name)}.lock"

    f = open(lock_path, "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        try:
            pid = int((f.read() or "0").strip() or "0")
        except ValueError:
            pid = 0
        f.close()
        if pid and _pid_alive(pid):
            return None
        logger.info("Stale lock found (pid=%s, not running); stealing.", pid)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        f = open(lock_path, "a+")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.close()
            return None

    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def _acquire_windows(name: str) -> Optional[Any]:
    try:
        import win32event
        import win32api
        import winerror
    except ModuleNotFoundError:
        logger.warning("pywin32 not available; single-instance enforcement skipped")
        return True  # non-None sentinel: allow startup

    handle = win32event.CreateMutex(None, False, f"Global\\{_key(name)}")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return None
    return handle


def acquire(name: str) -> Optional[Any]:
    """Try to claim the lock for `name`. Return handle to keep alive, or None."""
    if sys.platform == "win32":
        return _acquire_windows(name)
    return _acquire_posix(name)
