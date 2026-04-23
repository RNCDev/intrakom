"""Per-OS filesystem locations for Intrakom (config, logs, locks)."""

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    return Path.home() / ".intrakom"


def lock_dir() -> Path:
    return config_dir() / "locks"


def log_dir(component: str) -> Path:
    """
    component is "receiver" or "hub".
    Hub logs on Linux use journald, so log_dir is only meaningful for the
    receiver on Linux; callers for the hub on Linux should not write files.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Intrakom"
    if sys.platform == "win32":
        if component == "hub":
            base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        else:
            base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "Intrakom" / "Logs"
    return config_dir() / "logs"
