"""Install or remove the read-only runtime observer in LM Studio's pinned MLX engine.

Owner order of 29 September 2026: verify the actual execution configuration, not the
accepted client parameters. Separate from the prompt-cache hook and the retired
reasoning-budget hook.

- **pinned**: refuses unless the engine's files match the digests below, the engine the
  observer was written against (`mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`,
  `app-mlx-generate-mac14-arm64@34`);
- **reproducible**: copies `val_runtime_observer.py` and writes `val_runtime_observer.pth`
  (one line: `import val_runtime_observer; val_runtime_observer.activate()`) into that
  engine's site-packages, and prints their digests;
- **reversible**: `remove` deletes exactly those two files;
- **inert until listed**: `~/.lmstudio/val-runtime-observer.json` names the model
  directories it observes. With no allowlist it observes none.

It takes effect for a model instance at its next load. Usage: install.py install|remove|status
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
    "mlx_engine/generate.py": "ffd9279a7bedc5bf6a6fa983e0e30d2177f8926c5859b4dffc45bcc6e1febe81",
    "mlx_lm/generate.py": "35f77a8daacfd8a721236f7246406dd757f6947a4649dd54d2a59550c0f2bd15",
}
MODULE = "val_runtime_observer.py"
PTH = "val_runtime_observer.pth"
PTH_LINE = "import val_runtime_observer; val_runtime_observer.activate()\n"


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
        print("removed; the runtime observer's files are gone")
    else:
        present = [name for name in (MODULE, PTH) if (SITE / name).exists()]
        print({"engine_matches_pin": not check_engine(), "installed": present})


if __name__ == "__main__":
    main()
