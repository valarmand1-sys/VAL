"""One perception run, inside the house's isolated MLX-VLM runtime.

Owner ruling, 22 September 2026. This file is executed by
`~/.val-runtimes/mlx-vlm-venv/bin/python`, which is a **different interpreter
from Val's** — a separate environment with mlx, mlx-vlm and opencv in it, none
of which are production dependencies and none of which this ruling permits to
become production dependencies. That is why the boundary is a process rather
than an import: keeping the visual runtime out of Val's pinned environment is a
constraint of the order, not an accident of layout.

**It imports nothing from Val.** Not the domain, not the policy package, not the
gateway. It receives one JSON request on **stdin** and writes one JSON response
on **stdout**, and that is its entire contract. Nothing reaches it through the
command line, so no value from a model, a document or a tool result can become
an argument — the charter's arbitrary-command-path invariant is kept by there
being no path to steer, not by sanitising one.

**It holds nothing.** The process runs one request and exits, which is how the
visual model's memory is released: sequential residency is the architecture, and
a process that has exited is the most reliable release there is. Qualification
measured exactly this — wired memory returned from 13.10 GB to 2.97 GB on exit,
and GPT-OSS reloaded afterwards at its full registered window.

**It does not tune.** The generation settings are the MLX-VLM library defaults,
frozen before Qwen3.5's acceptance test ran and unchanged since; they are read
back from the runtime and returned, so the record says what governed rather than
what was intended.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from typing import Any

#: The frozen generation configuration, by absence: nothing is passed to
#: `generate()`, so the library's own defaults govern. Committed at `f0c81dd`
#: before either acceptance case ran. A keyword added here would be a change to
#: the admitted configuration and needs its own ruling.
GENERATE_KWARGS: dict[str, Any] = {}


def _fail(reason: str, *, kind: str = "unavailable") -> int:
    json.dump({"ok": False, "kind": kind, "reason": reason}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def main() -> int:
    request = json.load(sys.stdin)
    model_path = request["model_path"]
    prompt = request["prompt"]
    sources = request["sources"]
    if not sources:
        return _fail("a perception run needs at least one source", kind="refused")

    from mlx_vlm import __version__ as mlx_vlm_version
    from mlx_vlm import generate, load
    from mlx_vlm.generate import common as generation
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config, load_video

    started = time.monotonic()
    model, processor = load(model_path)
    config = load_config(model_path)
    loaded_seconds = time.monotonic() - started

    observations = []
    delivery: dict[str, Any] = {}
    for source in sources:
        path, modality = source["path"], source["modality"]
        # The bytes are checked here too, in the runtime that will actually read
        # them. The caller checked them against the record; this checks that what
        # reached the disk is what the caller meant to hand over. Evidence about
        # the wrong medium is worse than no evidence.
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if digest != source["sha256"]:
            return _fail(
                f"the file written for {source['sha256'][:12]} hashes to {digest[:12]}",
                kind="refused",
            )

        if modality == "image":
            formatted = apply_chat_template(processor, config, prompt, num_images=1)
            answer = generate(model, processor, formatted, image=[path], **GENERATE_KWARGS)
        elif modality == "video":
            # `video=` is what emits the video placeholder; there is no
            # `num_videos` parameter, and passing one is silently swallowed —
            # the defect found and recorded during the Qwen2.5-VL run.
            frames, meta = load_video(path)  # default sampling, deliberately unparameterised
            delivery[source["sha256"]] = {
                "source_total_frames": meta.total_num_frames,
                "source_fps": meta.fps,
                "duration_seconds": meta.duration,
                "frames_delivered": len(meta.frames_indices),
                "frame_indices": [int(index) for index in meta.frames_indices],
                "timestamps_seconds": [round(float(t), 3) for t in meta.timestamps],
                "sampled_fps": round(float(meta.sampled_fps), 4),
                "frames_array_shape": list(getattr(frames, "shape", [])),
            }
            formatted = apply_chat_template(processor, config, prompt, video=path)
            answer = generate(model, processor, formatted, video=[path], **GENERATE_KWARGS)
        else:
            # Audio is not admitted and is not reachable. Reaching this line
            # would mean something above this file invented a modality.
            return _fail(f"{modality!r} is not an admitted perception modality", kind="refused")

        text = answer.text if hasattr(answer, "text") else str(answer)
        observations.append(
            {"sha256": source["sha256"], "modality": modality, "text": text.strip()}
        )

    quantization = config.get("quantization") if isinstance(config, dict) else None
    json.dump(
        {
            "ok": True,
            "observations": observations,
            "video_delivery": delivery,
            "runtime": "mlx-vlm",
            "runtime_version": mlx_vlm_version,
            "model_type": (config.get("model_type") if isinstance(config, dict) else None),
            "quantization": quantization,
            "generation": {
                # Read back from the runtime, not restated from memory.
                "max_tokens": generation.DEFAULT_MAX_TOKENS,
                "temperature": generation.DEFAULT_TEMPERATURE,
                "top_p": generation.DEFAULT_TOP_P,
                "top_k": generation.DEFAULT_TOP_K,
                "min_p": generation.DEFAULT_MIN_P,
                "repetition_penalty": None,
                "eos_token_id": model.config.eos_token_id,
                "kwargs_passed_to_generate": sorted(GENERATE_KWARGS),
            },
            "load_seconds": round(loaded_seconds, 3),
            "duration_seconds": round(time.monotonic() - started, 3),
        },
        sys.stdout,
        default=str,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    # The boundary is a process, so it reports its failure rather than crashing
    # into a traceback the caller would have to parse.
    except Exception as failure:
        raise SystemExit(_fail(f"{type(failure).__name__}: {failure}")) from failure
