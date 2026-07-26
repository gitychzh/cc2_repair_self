#!/usr/bin/env python3
"""NV-unified proxy entry point — ThreadedHTTPServer startup — R38.12."""
import os
import sys
from http.server import ThreadingHTTPServer

from gateway.config import (
    LISTEN_HOST, LISTEN_PORT, PROXY_ROLE,
    NVU_NUM_KEYS,
    NVCF_PEXEC_MODELS,
    NV_MODEL_TIERS, DEFAULT_NV_MODEL,
)
from gateway.handlers import ProxyHandler


def create_and_start_server():
    print(f"[NV-PROXY] Starting NV-unified proxy on {LISTEN_HOST}:{LISTEN_PORT}", file=sys.stderr, flush=True)
    print(f"[NV-PROXY] PROXY_ROLE={PROXY_ROLE} NVU_NUM_KEYS={NVU_NUM_KEYS} "
           f"NVCF_pexec_models={list(NVCF_PEXEC_MODELS.keys())} "
           f"tiers={NV_MODEL_TIERS} default={DEFAULT_NV_MODEL}", file=sys.stderr, flush=True)

    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    print(f"[NV-PROXY] Listening on {LISTEN_HOST}:{LISTEN_PORT} "
           f"(role={PROXY_ROLE}, default_tier={DEFAULT_NV_MODEL}, "
           f"fallback_chain={NV_MODEL_TIERS})", file=sys.stderr, flush=True)
    server.serve_forever()
