from __future__ import annotations

import socket
import ssl
import time
from collections.abc import Callable
from typing import TypeVar


try:
    import httpx
    HTTPX_ERRORS = (httpx.TransportError, httpx.NetworkError, httpx.TimeoutException)
except ImportError:
    HTTPX_ERRORS = ()

Result = TypeVar("Result")


def _is_transient(error: Exception) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError, socket.timeout, ssl.SSLError, *HTTPX_ERRORS)):
        return True
    cause = getattr(error, "__cause__", None)
    if cause and _is_transient(cause):
        return True
    err_type_name = type(error).__name__.lower()
    if any(k in err_type_name for k in ("connect", "network", "transport", "ssl", "timeout", "socket")):
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
            "ssl",
            "bad record mac",
            "decryption failed",
            "handshake",
            "closed",
            "broken pipe",
            "eof occurred in violation of protocol",
        )
    )


def retry_supabase(operation: Callable[[], Result], attempts: int = 3) -> Result:
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            last_err = error
            if attempt == attempts - 1 or not _is_transient(error):
                raise
            time.sleep(0.15 * (2**attempt))
    if last_err:
        raise last_err
    raise RuntimeError("Supabase operation did not return")
