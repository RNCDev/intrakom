"""Central logging configuration for hub and receiver."""

import logging
import logging.handlers
import os
import sys

from intrakom import paths

_configured = False


def configure_logging(component: str) -> None:
    """
    Configure root logger with a rotating file handler and a stdout handler.
    component is "receiver" or "hub" — controls the log file name and path.
    Idempotent — safe to call multiple times.
    """
    global _configured
    if _configured:
        return
    _configured = True

    level = logging.DEBUG if os.environ.get("INTRAKOM_DEBUG") else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    directory = paths.log_dir(component)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            directory / f"{component}.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("File logging disabled: %s", exc)
