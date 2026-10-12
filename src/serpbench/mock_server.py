"""A tiny local server that imitates three SERP API response shapes.

It exists ONLY to test the rig (CI, development without keys). Latencies and
failure rates here are arbitrary numbers I picked; they say nothing about any
real vendor, and the providers are called mock_fast / mock_slow / mock_flaky on
purpose.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PROFILES = {
    "fast": {"median_ms": 350, "sigma": 0.25, "fail": 0.01, "shift": 0, "drop_snippet": 0.0},
    "slow": {"median_ms": 1200, "sigma": 0.35, "fail": 0.02, "shift": 2, "drop_snippet": 0.05},
    "flaky": {"median_ms": 500, "sigma": 0.40, "fail": 0.15, "shift": 0, "drop_snippet": 0.25},
}
SHAPES = {"/api/v1/search": "organic_results", "/search.json": "organic_results",
          "/search": "organic"}


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def make_server(port: int = 8765, seed: int = 42, speed: float = 1.0) -> ThreadingHTTPServer:
    rng = random.Random(seed)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _send(self, code: int, payload) -> None:
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _handle(self) -> None:
            parts = urlsplit(self.path)
            segs = parts.path.split("/", 2)  # ['', profile, rest]
            if len(segs) < 3 or segs[1] not in PROFILES:
                return self._send(404, {"error": "unknown mock profile"})
            prof = PROFILES[segs[1]]
            rest = "/" + segs[2]
            key = SHAPES.get(rest)
            if key is None:
                return self._send(404, {"error": "unknown mock path"})

            if self.command == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                q = (json.loads(self.rfile.read(length) or b"{}")).get("q", "")
            else:
                q = (parse_qs(parts.query).get("q") or [""])[0]

            delay = rng.lognormvariate(math.log(prof["median_ms"]), prof["sigma"]) / 1000.0
            time.sleep(min(delay, 3.0) * speed)

            roll = rng.random()
            if roll < prof["fail"]:
                if roll < prof["fail"] / 2:
                    return self._send(429, {"error": "rate limited (mock)"})
                return self._send(500, b"<html>boom (mock)</html>")

            base = _h(q)[:8]
            urls = [f"https://example.org/{base}/{i}" for i in range(12)]
            items = []
            for pos, i in enumerate(range(prof["shift"], prof["shift"] + 10), start=1):
                dropped = int(_h(q + str(i))[:4], 16) / 0xFFFF < prof["drop_snippet"]
                items.append({"position": pos, "title": f"Result {i} for {q}", "link": urls[i],
                              "snippet": "" if dropped else f"Snippet {i} about {q}."})
            self._send(200, {key: items})

        do_GET = _handle
        do_POST = _handle

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_in_thread(port: int = 0, seed: int = 42, speed: float = 1.0):
    srv = make_server(port, seed, speed)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]
