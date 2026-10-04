from __future__ import annotations

import socket
import ssl
import time
from collections.abc import Callable
from typing import TypeVar


Result = TypeVar("Result")


def _is_transient(error: Exception) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError, socket.timeout, ssl.SSLError)):
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "connection reset",
            "connection aborted",
            "connection refused",
            "read error",
            "timed out",
            "timeout",
            "temporarily unavailable",
        )
    )


def retry_supabase(operation: Callable[[], Result], attempts: int = 2) -> Result:
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            if attempt == attempts - 1 or not _is_transient(error):
                raise
            time.sleep(0.1 * (2**attempt))
    raise RuntimeError("Supabase operation did not return")
