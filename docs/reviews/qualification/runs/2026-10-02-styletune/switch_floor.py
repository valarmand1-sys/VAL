"""The floor of the Voice → typing switch, measured without any integration — T5, service level.

The Voice model and the typed candidate are different files, so the first typed request
after Voice needs the Voice server gone, the candidate's server up, and the request's
prompt prefilled. This script measures exactly that sequence with the installed runtime
and the house's own server flags, on its own port (8097) with its own two processes, and
nothing else: no Val service, no production resource.

  1. start the Voice model's server and answer one short request (as after a session);
  2. t0: stop it; start the candidate's server; wait until it answers /health;
  3. send one streamed chat request whose system message is the persona (the size of a
     real typed turn's stable prefix) and whose user message is one sentence;
  4. report t0 → server ready, ready → first visible token, and the total.

This is a floor: Core's own work, the recorded prime and the desktop are not in it, and
the file cache is whatever the machine holds (stated in the result). If the floor already
exceeds the registered threshold, no integration can pass T5 under one model at a time.

Usage: switch_floor.py OUT.json
"""

from __future__ import annotations

# ruff: noqa: S603, S101
import json
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[5]
MODELS = Path.home() / ".val-models/voice-candidates"
VOICE = MODELS / "gemma-4-26B-A4B-it-Q4_K_M.gguf"
TYPED = MODELS / "Gemma-4-26B-A4B-StyleTune-V2.Q4_K_M.gguf"
SERVER = "/opt/homebrew/bin/llama-server"
PORT = 8097
BASE = f"http://127.0.0.1:{PORT}"
KEY = secrets.token_hex(24)  # this run's throwaway key; never printed or stored
HEADERS = {"Authorization": f"Bearer {KEY}"}
PERSONA = (ROOT / "docs/baselines/03-persona.md").read_text()
SCRATCH = Path(sys.argv[1]).resolve().parent


def start(path: Path, alias: str) -> subprocess.Popen[bytes]:
    keyfile = SCRATCH / f".floor-key-{alias}"
    keyfile.write_text(KEY)
    keyfile.chmod(0o600)
    flags = [
        SERVER, "-m", str(path), "--alias", alias, "--ctx-size", "32768", "--parallel", "1",
        "--jinja", "-ngl", "999", "--host", "127.0.0.1", "--port", str(PORT),
        "--api-key-file", str(keyfile), "--swa-full", "-b", "2048", "-ub", "2048", "--no-webui",
        "--chat-template-kwargs", '{"enable_thinking":false}',
    ]  # fmt: skip
    child = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(1800):
        if child.poll() is not None:
            raise SystemExit(f"{alias}: the server exited while loading")
        try:
            if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                keyfile.unlink(missing_ok=True)
                return child
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise SystemExit(f"{alias}: not ready")


def first_token(alias: str, system: str, user: str) -> tuple[float, float, dict]:
    body = {
        "model": alias, "stream": True, "max_tokens": 200, "temperature": 1.0, "top_p": 0.95,
        "top_k": 64, "stream_options": {"include_usage": True},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }  # fmt: skip
    sent = time.monotonic()
    first = None
    usage: dict = {}
    with httpx.stream(
        "POST", f"{BASE}/v1/chat/completions", json=body, headers=HEADERS, timeout=300
    ) as r:
        for raw in r.iter_lines():
            if not raw.startswith("data: ") or raw == "data: [DONE]":
                continue
            chunk = json.loads(raw[6:])
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                if first is None and ((choice.get("delta") or {}).get("content") or "").strip():
                    first = time.monotonic()
    return (first or time.monotonic()) - sent, time.monotonic() - sent, usage


def main() -> int:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        assert probe.connect_ex(("127.0.0.1", PORT)) != 0, f"port {PORT} is in use: not starting"
    result: dict = {"port": PORT, "persona_chars": len(PERSONA)}
    began = time.monotonic()
    children: list[subprocess.Popen[bytes]] = []
    try:
        return measure(result, began, children)
    finally:  # whatever happens, this script's own servers are stopped
        for child in children:
            if child.poll() is None:
                child.terminate()


def measure(result: dict, began: float, children: list[subprocess.Popen[bytes]]) -> int:
    voice = start(VOICE, "floor-voice")
    children.append(voice)
    result["voice_model_load_s"] = round(time.monotonic() - began, 2)
    first_token("floor-voice", PERSONA, "Good evening, Val.")  # the session it has just had
    t0 = time.monotonic()
    voice.terminate()
    voice.wait(timeout=30)
    result["voice_model_stopped_s"] = round(time.monotonic() - t0, 2)
    typed = start(TYPED, "floor-typed")
    children.append(typed)
    result["t0_to_candidate_ready_s"] = round(time.monotonic() - t0, 2)
    onset, complete, usage = first_token(
        "floor-typed", PERSONA, "What makes a good opening line for a film?"
    )
    result["ready_to_first_visible_s"] = round(onset, 2)
    result["t0_to_first_visible_s"] = round(time.monotonic() - t0 - (complete - onset), 2)
    result["prompt_tokens"] = usage.get("prompt_tokens")
    # A second request, prefix now cached by the server: the steady state for comparison.
    onset2, _, usage2 = first_token("floor-typed", PERSONA, "And for a novel?")
    result["second_request_first_visible_s"] = round(onset2, 2)
    result["second_prompt_tokens"] = usage2.get("prompt_tokens")
    typed.terminate()
    typed.wait(timeout=30)
    Path(sys.argv[1]).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
