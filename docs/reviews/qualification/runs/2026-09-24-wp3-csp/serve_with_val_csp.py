"""Serve this directory under VAL's exact desktop CSP — WP3 CSP diagnosis.

The policy string is copied verbatim from `apps/desktop/src-tauri/tauri.conf.json`
so the probe is run under the real application's policy and not a paraphrase of it.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4].parents[0]
CONF = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
CSP = json.loads(CONF.read_text())["app"]["security"]["csp"]


class WithVoiceCsp(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    print(f"policy: {CSP}")
    print(f"serving {pathlib.Path(__file__).parent} on http://127.0.0.1:{port}")
    http.server.HTTPServer(("127.0.0.1", port), WithVoiceCsp).serve_forever()
