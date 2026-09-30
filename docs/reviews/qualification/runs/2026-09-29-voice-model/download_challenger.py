"""Download the challenger's one pinned file — CHALLENGER.md §1.3 — and nothing else.

Refuses to start without room for the file and a margin; verifies the SHA-256 against the
pin before reporting success; removes a mismatching file. The `.incomplete` part is written
in the target directory, so no second copy is ever needed.

Usage: uv run --project ROOT --with huggingface_hub python download_challenger.py
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "ggml-org/Qwen3.6-35B-A3B-GGUF"
REVISION = "baec3ebee244827cda0f4557eafa8b28f7545fa6"  # main as of 29 September 2026
FILE = "Qwen3.6-35B-A3B-Q4_K_M.gguf"
SHA256 = "671e47e0ec53c665d048b98c3ecbfd5236b5ca9c3e02ed19fc8f81f7b85140c7"
SIZE_GB = 20.4
MARGIN_GB = 2.0
TARGET_DIR = Path.home() / ".val-models" / "voice-candidates"

free_gb = shutil.disk_usage(TARGET_DIR).free / 1e9
if free_gb < SIZE_GB + MARGIN_GB:
    sys.exit(f"not started: {free_gb:.1f} GB free, {SIZE_GB + MARGIN_GB:.1f} GB needed (file + margin)")
print(f"{free_gb:.1f} GB free; downloading {FILE} ({SIZE_GB} GB) from {REPO}@{REVISION}")
path = Path(
    hf_hub_download(
        REPO,
        FILE,
        revision=REVISION,
        local_dir=str(TARGET_DIR),
        local_dir_use_symlinks=False,
    )
)
digest = hashlib.sha256()
with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(1 << 24), b""):
        digest.update(chunk)
if digest.hexdigest() != SHA256:
    path.unlink()
    sys.exit(f"SHA-256 mismatch: got {digest.hexdigest()[:16]}…; file removed")
print(f"verified {path} sha256 {SHA256[:16]}…; {shutil.disk_usage(TARGET_DIR).free / 1e9:.1f} GB free")
