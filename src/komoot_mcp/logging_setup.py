"""JSON-lines logging — same pattern as strava-mcp / pixel-mcp."""

from __future__ import annotations

import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        for key in ("event", "method", "path", "status", "duration_ms",
                     "attempt", "body", "exc", "retry_after_s", "reason"):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val
        if record.exc_info and not getattr(record, "exc", None):
            import traceback
            obj["exc"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(obj, ensure_ascii=False)


_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    log_dir = Path(os.path.expanduser("~/.config/komoot-mcp/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("komoot-mcp")
    level = os.environ.get("KOMOOT_MCP_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    # Ne pas remonter au handler racine de FastMCP (sinon chaque requete est aussi ecrite sur stderr)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_dir / "komoot-mcp.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)

    logger.info("logging initialized", extra={"event": "startup"})
    _logger = logger
    return logger
