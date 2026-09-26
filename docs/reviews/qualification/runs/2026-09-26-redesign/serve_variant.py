"""The scratch service of the priming pass, with one switch — targeted voice latency order.

`VAL_SCRATCH_FIRST_PAUSE=off` restores the segmenter's previous first-segment rule
(a first sentence is cut only past 220 characters) inside this process alone, so the
new rule can be measured against the old one on otherwise identical code. Nothing
on disk changes; production is not touched.
"""

from __future__ import annotations

import os
import runpy
from pathlib import Path

from val_policy.speech_segments import SpeechSegmenter

if os.environ.get("VAL_SCRATCH_FIRST_PAUSE", "on") == "off":
    defaults = SpeechSegmenter.__init__.__kwdefaults__
    assert defaults is not None
    defaults["first_soft_limit"] = 10**6

runpy.run_path(
    str(Path(__file__).resolve().parent.parent / "2026-09-25-priming/serve_scratch.py"),
    run_name="__main__",
)
