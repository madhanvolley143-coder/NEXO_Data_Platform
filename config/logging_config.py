"""
NEXO Data Platform - Structured Logging Configuration
Provides sanitizing log formatting to prevent credential leakage.
"""

import logging
import os
import re
import sys
from typing import Optional

# Patterns matching sensitive credentials, tokens, and keys
SENSITIVE_PATTERNS = [
    re.compile(r"sbp_[a-zA-Z0-9_\-]+", re.IGNORECASE),
    re.compile(r"eyJh[a-zA-Z0-9_\-\.]+", re.IGNORECASE),  # JWTs
    re.compile(r"(?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?([^'\"\s]+)", re.IGNORECASE),
]


class CredentialSanitizingFilter(logging.Filter):
    """
    Log filter that intercepts and redacts secret keys, JWT tokens,
    and passwords before output to stdout or files.
    """

    def __init__(self, name: str = ""):
        super().__init__(name)
        # Dynamically include any known environment secrets if loaded
        self.exact_secrets = []
        for var in ["SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]:
            val = os.getenv(var)
            if val and len(val.strip()) > 8:
                self.exact_secrets.append(val.strip())

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._sanitize(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self._sanitize(v) if isinstance(v, str) else v for v in record.args)
        return True

    def _sanitize(self, text: str) -> str:
        for secret in self.exact_secrets:
            text = text.replace(secret, "[REDACTED_SECRET]")
        for pattern in SENSITIVE_PATTERNS:
            text = pattern.sub("[REDACTED_KEY]", text)
        return text


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> None:
    """Configures the root NEXO logger with sanitization and formatting."""
    root_logger = logging.getLogger("nexo")
    root_logger.setLevel(level)

    # Avoid duplicate handlers
    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        console_handler.addFilter(CredentialSanitizingFilter())
        root_logger.addHandler(console_handler)

        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(CredentialSanitizingFilter())
            root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Convenience getter for namespaced NEXO loggers."""
    setup_logging()
    return logging.getLogger(f"nexo.{name}")
