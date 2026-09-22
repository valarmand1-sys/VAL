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
FPS = 10
SQUARE = 90
CIRCLE = 70
#: Seconds in each phase: the square still on the left, crossing, still on the
#: right, then the circle present beneath it. 8 seconds in total.
HOLD_LEFT, CROSS, HOLD_RIGHT, WITH_CIRCLE = 1.5, 3.0, 1.0, 2.5

LEFT_X = 60
RIGHT_X = WIDTH - 60 - SQUARE
SQUARE_Y = 120


def square_x(frame: int) -> int:
    """Where the square is on this frame, by phase."""
    hold = int(HOLD_LEFT * FPS)
    cross = int(CROSS * FPS)
    if frame < hold:
        return LEFT_X
    if frame < hold + cross:
        progress = (frame - hold) / cross
        return int(LEFT_X + (RIGHT_X - LEFT_X) * progress)
    return RIGHT_X


def main(destination: str) -> int:
    total = int((HOLD_LEFT + CROSS + HOLD_RIGHT + WITH_CIRCLE) * FPS)
    circle_from = int((HOLD_LEFT + CROSS + HOLD_RIGHT) * FPS)
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
