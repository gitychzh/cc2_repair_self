#!/usr/bin/env python3
"""ms_gw entry point — ThreadingHTTPServer startup."""
import os
import sys
from http.server import ThreadingHTTPServer

from gateway.config import (
    LISTEN_HOST, LISTEN_PORT, PROXY_ROLE,
    NUM_KEYS, NUM_VARIANTS, MODEL_REGISTRY, DEFAULT_MODEL, MS_BASEURL,
)
from gateway.handlers import ProxyHandler


def create_and_start_server():
    print(f"[MS-PROXY] Starting MS-unified proxy on {LISTEN_HOST}:{LISTEN_PORT}",
          file=sys.stderr, flush=True)
    print(f"[MS-PROXY] PROXY_ROLE={PROXY_ROLE} NUM_KEYS={NUM_KEYS} "
          f"NUM_VARIANTS={NUM_VARIANTS} models={list(MODEL_REGISTRY.keys())} "
          f"default={DEFAULT_MODEL} baseurl={MS_BASEURL}", file=sys.stderr, flush=True)
    if NUM_KEYS == 0:
        print("[MS-PROXY] FATAL: NUM_KEYS=0 — refusing to serve. Check MS_KEY1..N env.",
              file=sys.stderr, flush=True)

    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    print(f"[MS-PROXY] Listening on {LISTEN_HOST}:{LISTEN_PORT} "
          f"(role={PROXY_ROLE}, default={DEFAULT_MODEL})",
          file=sys.stderr, flush=True)
    server.serve_forever()
