"""Logging setup."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure standard library logging."""
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))

