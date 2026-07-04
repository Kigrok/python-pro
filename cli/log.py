#!/usr/bin/env python3
# cli/log.py — Centralized logging with JSON structured output.

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Final

_LOG_DIR: Final[Path] = Path.home() / ".cache" / "python-pro" / "logs"
_LOG_FILE: Final[Path] = _LOG_DIR / "python-pro.log"
_JSON_LOG_FILE: Final[Path] = _LOG_DIR / "python-pro.jsonl"
_LEVEL: Final[int] = logging.DEBUG


class JsonFormatter(logging.Formatter):
    """JSON log formatter for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "func": record.funcName,
            "line": record.lineno,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }
        # Add extra fields.
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class PerfFilter(logging.Filter):
    """Filter that adds performance timestamp to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.perf_ts = time.perf_counter_ns()  # type: ignore[attr-defined]
        return True


def setup_logging() -> logging.Logger:
    """Configure logging for the python-pro plugin."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger: logging.Logger = logging.getLogger("python-pro")
    logger.setLevel(_LEVEL)

    # Avoid duplicate handlers.
    if logger.handlers:
        return logger

    logger.addFilter(PerfFilter())

    # JSON file handler — structured logs for machine parsing.
    json_handler: logging.FileHandler = logging.FileHandler(
        _JSON_LOG_FILE,
        encoding="utf-8",
        delay=True,
    )
    json_handler.setLevel(_LEVEL)
    json_handler.setFormatter(JsonFormatter())
    logger.addHandler(json_handler)

    # Human-readable file handler — full debug output.
    file_handler: logging.FileHandler = logging.FileHandler(
        _LOG_FILE,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setLevel(_LEVEL)
    file_fmt: logging.Formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d %(message)s",
        datefmt="%H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # Stderr handler — warnings and above only.
    stderr_handler: logging.StreamHandler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_fmt: logging.Formatter = logging.Formatter(
        "[python-pro] %(levelname)s: %(message)s",
    )
    stderr_handler.setFormatter(stderr_fmt)
    logger.addHandler(stderr_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under python-pro namespace."""
    setup_logging()  # ensure configured
    return logging.getLogger(f"python-pro.{name}")


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    **kwargs: object,
) -> None:
    """Log a structured event with extra data.

    Usage:
        log_event(log, logging.INFO, "file_fixed",
                  file="cli/pipeline.py", issues=3, duration_ms=12.5)
    """
    record = logger.makeRecord(
        name=logger.name,
        level=level,
        fn="",
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_data = kwargs  # type: ignore[attr-defined]
    logger.handle(record)


# Module-level logger — import this anywhere.
log: Final[logging.Logger] = setup_logging()
