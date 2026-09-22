"""What the production sampler actually delivers for the repaired Case C fixture.

Uses MLX-VLM's default video sampling — nothing is passed to make the test
easier — and measures the red square and blue circle in every delivered frame,
so the sampled evidence can be judged rather than assumed.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from mlx_vlm.utils import load_video

VIDEO = sys.argv[1]
CONTACT = sys.argv[2] if len(sys.argv) > 2 else None

frames, meta = load_video(VIDEO)  # default sampling, deliberately unparameterised

arr = np.asarray(frames)
# (T, C, H, W) -> (T, H, W, C)
if arr.ndim == 4 and arr.shape[1] in (1, 3):
    arr = arr.transpose(0, 2, 3, 1)
if arr.dtype != np.uint8:
    arr = (arr * 255).clip(0, 255).astype(np.uint8) if arr.max() <= 1.0 else arr.astype(np.uint8)

width = arr.shape[2]


def locate(image: np.ndarray) -> dict:
    r, g, b = image[:, :, 0].astype(int), image[:, :, 1].astype(int), image[:, :, 2].astype(int)
    red = (r > 150) & (g < 100) & (b < 100)
    blue = (b > 150) & (r < 100) & (g < 100)

    def centre(mask):
        if not mask.any():
            return None
        ys, xs = np.nonzero(mask)
        return {
            "x": int(xs.mean()),
            "y": int(ys.mean()),
            "pixels": int(mask.sum()),
            "blobs": int(_blobs(mask)),
        }

    return {"red": centre(red), "blue": centre(blue)}


def _blobs(mask: np.ndarray) -> int:
    """How many separate runs of the colour appear on the widest row.

    A cheap duplicate-object check: one square gives one run, two squares give
    two. It is enough to catch the ambiguity the criterion forbids.
    """
    counts = mask.sum(axis=1)
    if counts.max() == 0:
        return 0
    row = mask[int(counts.argmax())]
    runs, previous = 0, False
    for value in row:
        if value and not previous:
            runs += 1
        previous = bool(value)
    return runs


report = {
    "source": {
        "total_frames": meta.total_num_frames,
        "fps": meta.fps,
        "duration_seconds": meta.duration,
        "width": meta.width,
        "height": meta.height,
    },
    "sampling": {
        "behaviour": "mlx_vlm.utils.load_video defaults (no arguments passed)",
        "frames_delivered": len(meta.frames_indices),
        "frame_indices": [int(i) for i in meta.frames_indices],
        "timestamps_seconds": [round(float(t), 3) for t in meta.timestamps],
        "sampled_fps": round(float(meta.sampled_fps), 4),
        "array_shape": list(arr.shape),
    },
    "frames": [],
}

third = width / 3
for position, (index, stamp) in enumerate(zip(meta.frames_indices, meta.timestamps)):
    found = locate(arr[position])
    red = found["red"]
    band = None
    if red:
        band = "left" if red["x"] < third else ("centre" if red["x"] < 2 * third else "right")
    report["frames"].append(
        {
            "n": position,
            "source_index": int(index),
            "t": round(float(stamp), 3),
            "red_x": red["x"] if red else None,
            "band": band,
            "red_blobs": red["blobs"] if red else 0,
            "circle": bool(found["blue"]),
            "circle_y_below_square": (
                bool(found["blue"]["y"] > red["y"]) if (found["blue"] and red) else None
            ),
        }
    )

xs = [f["red_x"] for f in report["frames"] if f["red_x"] is not None]
moving = [f for f in report["frames"] if f["red_blobs"] == 1]
distinct = sorted({f["red_x"] for f in report["frames"] if f["red_x"] is not None})
first_circle = next((f["t"] for f in report["frames"] if f["circle"]), None)
arrived = None
for f in report["frames"]:
    if f["red_x"] is not None and f["red_x"] == max(xs):
        arrived = f["t"]
        break
started = None
for f in report["frames"]:
    if f["red_x"] is not None and f["red_x"] > min(xs):
        started = f["t"]
        break

report["checks"] = {
    "distinct_red_positions": len(distinct),
    "intermediate_positions": len([x for x in distinct if min(xs) < x < max(xs)]),
    "monotonic_left_to_right": all(a <= b for a, b in zip(xs, xs[1:])),
    "never_more_than_one_red_blob": all(f["red_blobs"] <= 1 for f in report["frames"]),
    "bands_seen_in_order": [
        band
        for i, band in enumerate(f["band"] for f in report["frames"])
        if band and (i == 0 or band != report["frames"][i - 1]["band"])
    ],
    "movement_starts_at": started,
    "reaches_right_at": arrived,
    "circle_first_appears_at": first_circle,
    "circle_only_after_arrival": (
        None if (first_circle is None or arrived is None) else bool(first_circle > arrived)
    ),
    "circle_beneath_square_whenever_present": all(
        f["circle_y_below_square"] for f in report["frames"] if f["circle"]
    ),
}

if CONTACT:
    from PIL import Image, ImageDraw

    n = len(report["frames"])
    cols = 4
    rows = (n + cols - 1) // cols
    tw, th = 320, 240
    label = 26
    sheet = Image.new("RGB", (cols * tw, rows * (th + label)), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for i, f in enumerate(report["frames"]):
        thumb = Image.fromarray(arr[i]).resize((tw, th))
        x, y = (i % cols) * tw, (i // cols) * (th + label)
        sheet.paste(thumb, (x, y + label))
        draw.rectangle([x, y, x + tw, y + label], fill=(20, 20, 20))
        draw.text(
            (x + 8, y + 7),
            f"#{f['n']:02d}   t = {f['t']:.2f}s   source frame {f['source_index']}",
            fill=(255, 255, 255),
        )
        draw.rectangle([x, y + label, x + tw - 1, y + label + th - 1], outline=(200, 200, 200))
    sheet.save(CONTACT)
    report["contact_sheet"] = {"path": CONTACT, "size": list(sheet.size), "tiles": n}

print(json.dumps(report, indent=1))
