"""Logging configuration.

A single, process-wide logger named ``visual_studio``. Safe to call multiple
times (it is idempotent for the handler it installs).
"""

from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "visual_studio"
_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the shared ``visual_studio`` logger."""
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)

    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
        _CONFIGURED = True

    return logger


def get_logger() -> logging.Logger:
    """Return the shared logger, configuring defaults if necessary."""
    return configure_logging()
