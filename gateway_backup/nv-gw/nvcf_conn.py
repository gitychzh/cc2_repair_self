#!/usr/bin/env python3
"""NVCF connection layer — direct and SOCKS5-proxied HTTPS connections.

Extracted from upstream.py (Reng modularization). Logic is byte-for-byte
equivalent to the original; no behavioral change.

- _make_nvcf_direct_conn: direct TCP→SSL→HTTPSConnection (no proxy)
- _make_nvcf_proxy_conn: per-key mihomo SOCKS5 → SSL → HTTPSConnection.
  Empty/blank proxy_url falls back to a direct connection so per-key
  direct/proxy routing is controlled purely by NVU_PROXY_URL<n> env
  (empty=direct, non-empty=mihomo). Rproxy (HM1 self-change, authorized).
"""
import http.client
import socket
import ssl
import urllib.parse

import socks  # PySocks — SOCKS5 proxy support for NVCF pexec

from .config import UPSTREAM_TIMEOUT


def _make_nvcf_direct_conn(nvcf_host, timeout=UPSTREAM_TIMEOUT):
    """Create HTTPSConnection to NVCF API DIRECTLY (no proxy).

    R50: K1 and K2 use this function for direct NVCF API access.
    Connection flow: direct TCP → connect to nvcf_host:443
    → wrap with SSL → inject into HTTPSConnection.

    Args:
        nvcf_host: NVCF API hostname
        timeout: connect timeout

    Returns: HTTPSConnection with direct SSL socket, ready for request()
    """
    import ssl as _ssl_mod
    ctx = _ssl_mod.create_default_context()

    s = socket.create_connection((nvcf_host, 443), timeout=timeout)
    ss = ctx.wrap_socket(s, server_hostname=nvcf_host)

    conn = http.client.HTTPSConnection(nvcf_host, 443, timeout=timeout)
    conn.sock = ss
    return conn

def _make_nvcf_proxy_conn(proxy_url, nvcf_host, timeout=UPSTREAM_TIMEOUT):
    """Create HTTPSConnection to NVCF API via per-key mihomo SOCKS5 proxy.

    R38.12: ALL models use this function (no LiteLLM path).
    Connection flow: SOCKS5 socket → connect to nvcf_host:443 via mihomo
    → wrap with SSL → inject into HTTPSConnection.

    Args:
        proxy_url: e.g. "http://host.docker.internal:7894"
        nvcf_host: NVCF API hostname (from NVCF_BASE_URL config)
        timeout: connect timeout (read timeout set via sock.settimeout later)

    Returns: HTTPSConnection with SOCKS5-proxied SSL socket, ready for request()

    Rproxy (HM1 self-change, authorized): when proxy_url is empty/blank, fall back to
    a DIRECT connection (same as _make_nvcf_direct_conn) so per-key direct/proxy routing
    is controlled purely by NVU_PROXY_URL<n> env (empty=direct, non-empty=mihomo).
    Mirrors HM2 R295 logic. k2/k4 direct, k1/k3/k5 via mihomo on HM1.
    """
    # Empty proxy_url → direct NVCF connection (no mihomo)
    if not proxy_url or proxy_url.strip() == "":
        return _make_nvcf_direct_conn(nvcf_host=nvcf_host, timeout=timeout)

    parsed = urllib.parse.urlparse(proxy_url)
    proxy_host = parsed.hostname
    proxy_port = parsed.port or 7894

    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, proxy_host, proxy_port)
    s.settimeout(timeout)
    s.connect((nvcf_host, 443))

    ctx = ssl.create_default_context()
    ss = ctx.wrap_socket(s, server_hostname=nvcf_host)

    conn = http.client.HTTPSConnection(nvcf_host, 443, timeout=timeout)
    conn.sock = ss
    return conn
