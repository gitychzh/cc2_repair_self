#!/usr/bin/env python3
"""cc4101 gateway entry point.

R684: Serves Claude Code (cc2) on HM2 — Anthropic /v1/messages → glm5.2
(nv_gw glm5_2_nv + ms_gw glm5_2_ms fallback, R1711 透传 /v1/messages). Clean, isolated, glm5.2-only.
"""
import socketserver

from .config import LISTEN_HOST, LISTEN_PORT, UPSTREAM_TIMEOUT, UPSTREAM_IDLE_TIMEOUT, PROXY_ROLE
from .config import PRIMARY_UPSTREAM_MODEL, FALLBACK_UPSTREAM_URL, FALLBACK_UPSTREAM_MODEL
from .logger import _log


class ThreadedHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    from .handlers import ProxyHandler
    server = ThreadedHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    _log("START", f"cc4101 listening on {LISTEN_HOST}:{LISTEN_PORT} (role={PROXY_ROLE})")
    _log("START", f"  primary  : {PRIMARY_UPSTREAM_MODEL}")
    _fb = FALLBACK_UPSTREAM_URL or "(disabled)"
    _log("START", f"  upstream: nv_gw {PRIMARY_UPSTREAM_MODEL} /v1/messages")
    _log("START", f"  fallback: ms_gw {FALLBACK_UPSTREAM_MODEL} (R1643, breaker-OPEN triggered) -> {_fb}")
    _log("START", f"  UPSTREAM_TIMEOUT={UPSTREAM_TIMEOUT}s (connect+header, 死连接快断)")
    _log("START", f"  UPSTREAM_IDLE_TIMEOUT={UPSTREAM_IDLE_TIMEOUT}s (body read idle, 容纳thinking静默)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("STOP", "Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
