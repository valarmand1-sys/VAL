"""Qwen3-VL-8B-Instruct against the two frozen visual cases, run once each.

Case A uses the genuine Track C attachment and the repaired Case A criterion.
Case C uses the repaired fixture frozen at 53705f2, whose digest is checked
before inference — a run against the wrong bytes would prove nothing.

Untuned: library defaults, nothing passed to steer sampling, nothing changed
between cases. It also records what the runtime actually delivered for the video
so the answer can be judged against the evidence the model was shown.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

MODEL = "/Users/josepharmand/.val-models/Qwen3-VL-8B-Instruct-4bit"
FIX = Path(
    "/private/tmp/claude-501/-Users-josepharmand-Projects-val/"
    "6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/fixtures"
)
REPAIRED_VIDEO = Path(
    "/Users/josepharmand/Projects/val/docs/reviews/qualification/runs/"
    "2026-09-22-case-c-repair/case_c_video_v2.mp4"
)
REPAIRED_DIGEST = "6925c05c4ea8d164f172e0d16de775736ffccd0d62dd0c649fb9a354f680a169"
IMAGE_DIGEST = "7fc13a7c5072b69acc119d20a16beb6523dc21aa4ba6a4ef950c7ba748c12db0"

# Verbatim from FROZEN_ACCEPTANCE_TEST.md, committed in 0d41337. Unchanged.
PROMPT_A = (
    "Report only what you can actually see in this image. Do not guess, do not "
    "interpret motives, and do not add anything that is not visible. Cover: how many "
    "people are present; what the child is wearing; what the people are doing; the "
    "setting; and any major visible continuity details."
)
PROMPT_C = (
    "Describe what happens in this video and the order in which it happens. Report "
    "only what is visible."
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config, load_video

    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    report: dict[str, object] = {}

    started = time.monotonic()
    model, processor = load(MODEL)
    config = load_config(MODEL)
    report["load_seconds"] = round(time.monotonic() - started, 2)

    if which in ("a", "both"):
        image = FIX / "case_a_image.png"
        found = digest(image)
        report["case_a_source"] = {"path": str(image), "sha256": found, "matches": found == IMAGE_DIGEST}
        if found != IMAGE_DIGEST:
            raise SystemExit(f"Case A fixture digest mismatch: {found}")
        formatted = apply_chat_template(processor, config, PROMPT_A, num_images=1)
        start = time.monotonic()
        answer = generate(model, processor, formatted, image=[str(image)], verbose=False)
        report["case_a"] = {
            "seconds": round(time.monotonic() - start, 2),
            "answer": answer.text if hasattr(answer, "text") else str(answer),
        }

    if which in ("c", "both"):
        found = digest(REPAIRED_VIDEO)
        report["case_c_source"] = {
            "path": str(REPAIRED_VIDEO),
            "sha256": found,
            "matches_frozen": found == REPAIRED_DIGEST,
        }
        if found != REPAIRED_DIGEST:
            raise SystemExit(f"Case C fixture digest mismatch: {found}")

        frames, meta = load_video(str(REPAIRED_VIDEO))  # default sampling
        report["case_c_delivery"] = {
            "source_total_frames": meta.total_num_frames,
            "source_fps": meta.fps,
            "duration_seconds": meta.duration,
            "width": meta.width,
            "height": meta.height,
            "frames_delivered": len(meta.frames_indices),
            "frame_indices": [int(i) for i in meta.frames_indices],
            "timestamps_seconds": [round(float(t), 3) for t in meta.timestamps],
            "sampled_fps": round(float(meta.sampled_fps), 4),
            "frames_array_shape": list(getattr(frames, "shape", [])),
        }
        # `video=` is what triggers the video message formatter; `num_videos`
        # is not a parameter of this function — the defect found and recorded
        # during the Qwen2.5-VL run.
        formatted = apply_chat_template(processor, config, PROMPT_C, video=str(REPAIRED_VIDEO))
        report["case_c_prompt_rendered"] = formatted[:1200] if isinstance(formatted, str) else None
        start = time.monotonic()
        answer = generate(model, processor, formatted, video=[str(REPAIRED_VIDEO)], verbose=False)
        report["case_c"] = {
            "seconds": round(time.monotonic() - start, 2),
            "answer": answer.text if hasattr(answer, "text") else str(answer),
        }

    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
