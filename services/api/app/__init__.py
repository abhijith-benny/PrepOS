"""PrepOS API package."""
from __future__ import annotations

import ssl

# Ensure TLS stability on environments where TLS 1.3 encounters record MAC decryption issues
try:
    _orig_create_default_context = ssl.create_default_context

    def _tls12_default_context(*args, **kwargs):
        ctx = _orig_create_default_context(*args, **kwargs)
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    ssl.create_default_context = _tls12_default_context
    ssl._create_default_https_context = _tls12_default_context
except Exception:
    pass

try:
    import httpx

    _orig_httpx_create_ssl = httpx.create_ssl_context

    def _tls12_httpx_ssl(*args, **kwargs):
        ctx = _orig_httpx_create_ssl(*args, **kwargs)
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    httpx.create_ssl_context = _tls12_httpx_ssl
except Exception:
    pass
