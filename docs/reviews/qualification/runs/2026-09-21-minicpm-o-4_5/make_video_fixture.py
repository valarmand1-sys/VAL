"""Case C's fixture: one deterministic short local video.

A red square crosses the frame left → centre → right, and only then does a blue
circle appear beneath it. Nothing in the frame states the answer: there is no
text, no arrow and no caption, so a model that reports the order has read the
order out of the frames.

Drawn with Pillow and encoded with ffmpeg. Deterministic: the same inputs give
the same bytes, so the fixture can be regenerated and re-hashed.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 640, 480
#: One frame per second, eight frames, eight seconds.
#:
#: The frame rate is dictated by how the runtime actually delivers video, found
#: by reading it (`tools/server/ws_handler.cpp`): it runs
#: `ffmpeg -frames:v N` with no sampling filter and N capped at 8, which takes
#: the **first** N frames of the file and not N frames spread across it. At ten
#: frames a second the model would have been shown the first 0.8 seconds — the
#: square sitting still on the left — and asked to describe a movement it had
#: never seen. Encoding the sequence at one frame a second makes the runtime's
#: own selection cover the whole eight seconds. The sequence, the duration and
#: the criteria are unchanged; only the frame rate is, and it is changed so the
#: fixture reaches the model at all.
FPS = 1
SQUARE = 90
CIRCLE = 70

#: Where the square sits on each of the eight frames, left to right, and from
#: which frame the circle is present. Written out per frame rather than
#: interpolated, so every frame the model sees is unambiguous: two on the left,
#: one part-way, one at the centre, one part-way, then three on the right, with
#: the circle on the last two.
POSITIONS = ("left", "left", "quarter", "centre", "three_quarter", "right", "right", "right")
CIRCLE_FROM = 6

SQUARE_Y = 120
LEFT_X = 60
RIGHT_X = WIDTH - 60 - SQUARE
_PLACES = {
    "left": LEFT_X,
    "quarter": LEFT_X + (RIGHT_X - LEFT_X) // 4,
    "centre": (WIDTH - SQUARE) // 2,
    "three_quarter": LEFT_X + 3 * (RIGHT_X - LEFT_X) // 4,
    "right": RIGHT_X,
}


def square_x(frame: int) -> int:
    """Where the square is on this frame."""
    return _PLACES[POSITIONS[frame]]


def main(destination: str) -> int:
    total = len(POSITIONS)
    circle_from = CIRCLE_FROM
    with tempfile.TemporaryDirectory() as workspace:
        for frame in range(total):
            image = Image.new("RGB", (WIDTH, HEIGHT), (245, 245, 245))
            draw = ImageDraw.Draw(image)
            x = square_x(frame)
            draw.rectangle(
                [x, SQUARE_Y, x + SQUARE, SQUARE_Y + SQUARE], fill=(220, 30, 30)
            )
            if frame >= circle_from:
                centre_x = RIGHT_X + SQUARE // 2
                top = SQUARE_Y + SQUARE + 70
                draw.ellipse(
                    [centre_x - CIRCLE // 2, top, centre_x + CIRCLE // 2, top + CIRCLE],
                    fill=(30, 60, 220),
                )
            image.save(Path(workspace) / f"frame_{frame:04d}.png")
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-framerate", str(FPS),
                "-i", str(Path(workspace) / "frame_%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                destination,
            ],
            check=True,
        )
    print(f"wrote {destination}: {total} frames at {FPS} fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "case_c_video.mp4"))
