"""Case C's repaired fixture: one red square that actually travels.

The original fixture held the square at three positions and cut between them,
while the criterion asked a candidate to establish that one square *moves*
left, through centre, to right. Nothing in it moved. This one does: during the
travel phase every successive source frame puts the square somewhere new, so
the motion is in the source rather than implied by the criterion.

Deliberately unchanged from the original: the frame size, the light background,
one red square, one blue circle, and nothing else in the frame — no text, no
arrow, no label, no motion trail, no second square. The repair replaces the
defective motion representation, not the case.

Deterministic: the same inputs give the same bytes, so the fixture can be
regenerated and re-hashed.

    python make_video_fixture_v2.py <output.mp4>
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 640, 480
#: Well above the 24 fps floor the order sets, so the travel is smooth in the
#: source and the production sampler has a dense span to draw from.
FPS = 30

BACKGROUND = (245, 245, 245)
SQUARE = 90
CIRCLE = 70
RED = (220, 30, 30)
BLUE = (30, 60, 220)

SQUARE_Y = 120
LEFT_X = 60
RIGHT_X = WIDTH - 60 - SQUARE

#: Seconds. The square rests briefly on the left, travels for five seconds,
#: rests at the right, and only then is the circle added for the final hold.
#: The gap between the square stopping and the circle appearing is deliberate:
#: the circle must never appear while the square is still moving.
HOLD_LEFT = 1.0
TRAVEL = 5.0
HOLD_RIGHT = 1.0
WITH_CIRCLE = 2.0
TOTAL = HOLD_LEFT + TRAVEL + HOLD_RIGHT + WITH_CIRCLE  # 9.0 s


def square_x(frame: int) -> int:
    """Where the square is on this source frame.

    Linear travel: during the travel phase every successive frame advances the
    square by (RIGHT_X - LEFT_X) / (TRAVEL * FPS) pixels, about 3.4 px at these
    settings, so no two consecutive travel frames are identical.
    """
    hold_left = round(HOLD_LEFT * FPS)
    travel = round(TRAVEL * FPS)
    if frame < hold_left:
        return LEFT_X
    if frame < hold_left + travel:
        progress = (frame - hold_left) / travel
        return round(LEFT_X + (RIGHT_X - LEFT_X) * progress)
    return RIGHT_X


def circle_present(frame: int) -> bool:
    """Only after the square has arrived and held."""
    return frame >= round((HOLD_LEFT + TRAVEL + HOLD_RIGHT) * FPS)


def main(destination: str) -> int:
    total = round(TOTAL * FPS)
    with tempfile.TemporaryDirectory() as workspace:
        for frame in range(total):
            image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
            draw = ImageDraw.Draw(image)
            x = square_x(frame)
            draw.rectangle([x, SQUARE_Y, x + SQUARE, SQUARE_Y + SQUARE], fill=RED)
            if circle_present(frame):
                centre_x = RIGHT_X + SQUARE // 2
                top = SQUARE_Y + SQUARE + 70
                draw.ellipse(
                    [centre_x - CIRCLE // 2, top, centre_x + CIRCLE // 2, top + CIRCLE],
                    fill=BLUE,
                )
            image.save(Path(workspace) / f"frame_{frame:05d}.png")
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-framerate", str(FPS),
                "-i", str(Path(workspace) / "frame_%05d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                destination,
            ],
            check=True,
        )
    print(f"wrote {destination}: {total} frames at {FPS} fps, {TOTAL:g}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "case_c_video_v2.mp4"))
