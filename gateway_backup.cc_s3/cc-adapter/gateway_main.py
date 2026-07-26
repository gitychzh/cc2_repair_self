#!/usr/bin/env python3
"""cc-adapter 入口. 与 cx4102/gateway_main.py 同构."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway.app import AdapterHandler
from http.server import ThreadingHTTPServer
from gateway.config import LISTEN_HOST, LISTEN_PORT, PROXY_TIMEOUT, ADAPTER_NAME
from gateway.config import (
    PRIMARY_URL, FALLBACK_URL, PRIMARY_MODEL, FALLBACK_MODEL, FALLBACK_ENABLED,
)
from gateway.logger import _log


def main():
    _log("START", f"{ADAPTER_NAME} listening on {LISTEN_HOST}:{LISTEN_PORT}")
    _log("START", f"fallback_enabled={FALLBACK_ENABLED} proxy_timeout={PROXY_TIMEOUT}s")
    _log("START", f"primary={PRIMARY_URL}/{PRIMARY_MODEL} "
                  f"fallback={FALLBACK_URL}/{FALLBACK_MODEL}")
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), AdapterHandler)
    server.timeout = None
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("STOP", f"{ADAPTER_NAME} shutdown")
        server.shutdown()


if __name__ == "__main__":
    main()
