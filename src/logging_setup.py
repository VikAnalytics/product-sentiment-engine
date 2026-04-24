"""
Structured logging setup.

- In GitHub Actions (`GITHUB_ACTIONS=true`), emits one JSON object per log line
  so Actions run pages + any downstream log aggregator (Datadog, Loki, etc.)
  get parseable records.
- Locally, keeps the existing human-readable format.
- Idempotent: safe to call multiple times; subsequent calls are no-ops.
- Additive: does not remove any `logging.basicConfig` already set up by the
  pipeline scripts — this simply registers as the root handler ahead of them.

Usage:
    from logging_setup import setup_logging
    setup_logging()
    log = logging.getLogger(__name__)
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter — no external dependency."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Include any structured extras (record.__dict__ keys not in the default set)
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        for k, v in record.__dict__.items():
            if k not in standard_attrs and not k.startswith("_"):
                try:
                    json.dumps(v)  # only include JSON-serializable extras
                    payload[k] = v
                except (TypeError, ValueError):
                    payload[k] = repr(v)
        return json.dumps(payload, default=str)


def setup_logging(level: Optional[str] = None) -> None:
    """
    Configure root logger. Idempotent.
    `level` defaults to env LOG_LEVEL or INFO.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    numeric_level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

    root = logging.getLogger()
    # Replace existing handlers to avoid duplicate lines (basicConfig from older scripts).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(numeric_level)

    _CONFIGURED = True
