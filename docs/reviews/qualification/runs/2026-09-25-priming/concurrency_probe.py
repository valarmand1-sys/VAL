"""Two local requests at once: batched vs sequential serving — priming-cache pass §12.

Sends two production-shaped requests simultaneously to the isolated `val-exp`
instance and records when each produced its first output. Run once against a
parallel-4 load and once against parallel-1. Scratch content; nothing stored.
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
import threading
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        os.environ.setdefault(name, value)

from val_domain.gateway import Message  # noqa: E402
from val_domain.registry import by_slug  # noqa: E402
from val_providers.lmstudio_adapter import LMStudioAdapter  # noqa: E402

persona = Path(sys.argv[1]).read_text().strip()
config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner").model_copy(
    update={"model_identifier": "val-exp"}
)
adapter = LMStudioAdapter(token=os.environ["VAL_LMSTUDIO_API_TOKEN"], read_native_models=False)
results: dict[str, float] = {}


def ask(label: str, words: str) -> None:
    kwargs = adapter._request(config, (Message(role="user", content=words),), persona, 24, None)
    started = time.monotonic()
    for chunk in adapter._client.chat.completions.create(stream=True, **kwargs):
        if chunk.choices:
            results[label] = round(time.monotonic() - started, 3)
            break


threads = [threading.Thread(target=ask, args=("first", "Good evening, Val.")),
           threading.Thread(target=ask, args=("second", "What is on the calendar?"))]
for thread in threads:
    thread.start()
    time.sleep(0.05)
for thread in threads:
    thread.join()
print(json.dumps(results))
