"""Does shutting the socket down unblock a reader the runtime never answers? — §3, 27 Sept 2026.

The P4c/P4d runs: after `Stream.close()` from a watcher thread while the runtime was
prefilling, the server logged "Client disconnected. Stopping generation…", finished the
prefill, stopped — and never closed its side, so the reader thread stayed blocked on the
socket until the client's 600 s read timeout. Two variants, each on a **cold** prompt
(six distinct one-token prompts first push the checkpoints out), cancelled 1.0 s after
dispatch from another thread:

  A. `stream.close()` alone (what the adapter did);
  B. the raw socket's `shutdown(SHUT_RDWR)` through httpcore's `network_stream`
     extension, then `stream.close()`.

Measured: how long the reader thread stays blocked, what it raises, and how soon a
following request is served. Local, $0, one token per prompt. Usage: socket_shutdown_probe.py OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import socket
import sys
import threading
import time
from pathlib import Path

import openai

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    env = plistlib.load(handle)["EnvironmentVariables"]
base = env.get("VAL_LMSTUDIO_BASE_URL", os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"))
client = openai.OpenAI(base_url=base, api_key=env["VAL_LMSTUDIO_API_TOKEN"], timeout=600.0, max_retries=0)
MODEL = "openai/gpt-oss-20b"
PERSONA = Path("/Users/josepharmand/Projects/val/docs/baselines/03-persona.md").read_text()


def evict() -> None:
    for i in range(6):
        client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": " ".join(f"unrelated {i} token {j}" for j in range(40))}], max_tokens=1)


def trial(variant: str) -> dict:
    evict()
    result: dict = {"variant": variant}
    stream = client.chat.completions.create(
        model=MODEL, stream=True, max_tokens=64,
        messages=[{"role": "system", "content": PERSONA}, {"role": "user", "content": f"Probe {variant}: tell me about the invitation for the reading."}],
    )
    dispatched = time.monotonic()
    done = threading.Event()

    def cancel() -> None:
        time.sleep(1.0)
        t = time.monotonic()
        response = getattr(stream, "response", None)
        if variant == "B":
            ns = response.extensions.get("network_stream") if response is not None else None
            sock = ns.get_extra_info("socket") if ns is not None else None
            result["socket_found"] = sock is not None
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                    result["shutdown_ok"] = True
                except OSError as error:
                    result["shutdown_ok"] = f"{type(error).__name__}: {error}"
        try:
            stream.close()
        except Exception as error:  # noqa: BLE001
            result["close_error"] = f"{type(error).__name__}: {error}"
        result["cancel_at_s"] = round(t - dispatched, 3)
        result["cancel_took_s"] = round(time.monotonic() - t, 3)

    threading.Thread(target=cancel, daemon=True).start()
    chunks = 0
    try:
        for _chunk in stream:
            chunks += 1
        result["reader_ended"] = "exhausted"
    except Exception as error:  # noqa: BLE001
        result["reader_ended"] = f"{type(error).__name__}: {str(error)[:80]}"
    result["reader_blocked_s"] = round(time.monotonic() - dispatched, 3)
    result["chunks_before_end"] = chunks
    done.set()
    t = time.monotonic()
    follow = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "Say ok."}], max_tokens=1)
    result["next_request_s"] = round(time.monotonic() - t, 3)
    result["next_prompt_tokens"] = (follow.usage.prompt_tokens if follow.usage else None)
    return result


out = [trial("A"), trial("B")]
Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out))
