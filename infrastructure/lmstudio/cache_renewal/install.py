"""Install or remove the prompt-cache recency hook in LM Studio's pinned MLX engine.

Reproducible, version-pinned, reversible (owner order of 27 September 2026, §2):

- **pinned**: refuses unless the engine's files match the digests below — the engine the
  hook was written against (`mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`,
  `app-mlx-generate-mac14-arm64@34`);
- **reproducible**: copies `val_cache_renewal.py` and writes `val_cache_renewal.pth`
  (one line: `import val_cache_renewal; val_cache_renewal.activate()`) into that engine's
  site-packages, and records their digests;
- **reversible**: `remove` deletes exactly those two files; the engine is then byte-for-byte
  as shipped. The allowlist (`~/.lmstudio/val-cache-renewal.json`) decides which model
  directories the hook touches at all; with no allowlist it touches none.

It takes effect for a model instance at its next load; an instance already loaded keeps
the code it loaded with. Usage: install.py install|remove|status
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = "app-mlx-generate-mac14-arm64@34"
SITE = (
    Path.home()
    / ".lmstudio/extensions/backends/vendor/_amphibian"
    / ENGINE
    / "lib/python3.11/site-packages"
)
PINNED = {
    "mlx_lm/models/cache.py": "819ed95dcbf755652363cfdb15a639890447abb534a06dcefd52c7fff5055750",
    "mlx_engine/cache_wrapper.py": "ed23727e4ac00e23a61e61f4f361ad69d9a8391b8ae803506151ede29ac6f763",  # noqa: E501 - a digest is not wrapped
    "mlx_engine/model_kit/model_kit.py": "1e989e92a5c014f0ac2c89084d3605f1c1bb0592aed509a14743891a76321fc1",  # noqa: E501 - a digest is not wrapped
}
MODULE = "val_cache_renewal.py"
PTH = "val_cache_renewal.pth"
PTH_LINE = "import val_cache_renewal; val_cache_renewal.activate()\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_engine() -> list[str]:
    problems = []
    for relative, expected in PINNED.items():
        path = SITE / relative
        if not path.exists():
            problems.append(f"missing {relative}")
        elif digest(path) != expected:
            problems.append(f"{relative} differs from the pinned engine")
    return problems


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "install":
        problems = check_engine()
        if problems:
            sys.exit("refused: " + "; ".join(problems))
        shutil.copyfile(HERE / MODULE, SITE / MODULE)
        (SITE / PTH).write_text(PTH_LINE)
        print(
            f"installed: {MODULE} sha256={digest(SITE / MODULE)}; {PTH} sha256={digest(SITE / PTH)}"
        )
    elif action == "remove":
        for name in (MODULE, PTH):
            (SITE / name).unlink(missing_ok=True)
        print("removed; engine files as shipped")
    else:
        present = [name for name in (MODULE, PTH) if (SITE / name).exists()]
        print({"engine_matches_pin": not check_engine(), "installed": present})


if __name__ == "__main__":
    main()
