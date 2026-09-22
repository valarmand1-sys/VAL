"""Qwen2.5-VL against the frozen visual cases, run once each.

Two cases only: the image case with its repaired criterion, and the video case
unchanged. Audio is not tested and is not claimed.

Deliberately untuned: generation uses the library's defaults, nothing is passed
to steer sampling, and nothing changes between the two cases. The prompts are
the frozen ones, verbatim.

It also records what the runtime actually handed the model for the video —
source duration and rate, sampled rate, frame count, frame indices and their
timestamps — because a video answer cannot be judged without knowing what was
shown.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

MODEL = "/Users/josepharmand/.val-models/Qwen2.5-VL-7B-Instruct-4bit"
FIX = Path(
    "/private/tmp/claude-501/-Users-josepharmand-Projects-val/"
    "6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/fixtures"
)

# Verbatim from FROZEN_ACCEPTANCE_TEST.md, committed in 0d41337.
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


def main() -> int:
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config

    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    report: dict[str, object] = {}

    started = time.monotonic()
    model, processor = load(MODEL)
    config = load_config(MODEL)
    report["load_seconds"] = round(time.monotonic() - started, 2)

    if which in ("a", "both"):
        image = str(FIX / "case_a_image.png")
        formatted = apply_chat_template(processor, config, PROMPT_A, num_images=1)
        start = time.monotonic()
        answer = generate(model, processor, formatted, image=[image], verbose=False)
        report["case_a"] = {
            "seconds": round(time.monotonic() - start, 2),
            "source": image,
            "answer": answer.text if hasattr(answer, "text") else str(answer),
        }

    if which in ("c", "both"):
        video = str(FIX / "case_c_video.mp4")
        # What the runtime will actually sample, recorded from the same loader
        # the generation path uses.
        from mlx_vlm.utils import load_video

        frames, meta = load_video(video)
        report["case_c_delivery"] = {
            "source_total_frames": meta.total_num_frames,
            "source_fps": meta.fps,
            "duration_seconds": meta.duration,
            "width": meta.width,
            "height": meta.height,
            "frames_delivered": len(meta.frames_indices),
            "frame_indices": list(meta.frames_indices),
            "frame_timestamps_seconds": [round(t, 3) for t in meta.timestamps],
            "sampled_fps": round(meta.sampled_fps, 4),
            "frames_array_shape": list(getattr(frames, "shape", [])),
        }
        # The video placeholder is inserted only when the template is told which
        # video it is for: `apply_chat_template` takes `video=`, and has no
        # `num_videos` parameter at all. Passing the latter put it silently into
        # **kwargs, no placeholder was emitted, and the model was handed a bare
        # question about a video it had never been shown — it said so, and
        # answered in 1.1 s. Corrected here as an installation defect that
        # stopped the intended input reaching the model.
        formatted = apply_chat_template(processor, config, PROMPT_C, video=video)
        start = time.monotonic()
        answer = generate(model, processor, formatted, video=[video], verbose=False)
        report["case_c"] = {
            "seconds": round(time.monotonic() - start, 2),
            "source": video,
            "answer": answer.text if hasattr(answer, "text") else str(answer),
        }

    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
