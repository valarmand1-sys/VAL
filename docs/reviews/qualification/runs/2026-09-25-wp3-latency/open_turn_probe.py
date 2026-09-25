"""Time open_turn (new chat, sealed) on the scratch store, piece by piece."""

import cProfile
import io
import pstats
import time

from sqlalchemy import create_engine

from val_gateway.loop import open_turn
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_policy.project_resolution import ProjectSignals

engine = create_engine("postgresql+psycopg://localhost:5433/val_test")
cat = load_catalogue(engine)
for i in range(4):
    t = time.monotonic()
    open_turn(
        engine,
        "Good evening, Val.",
        catalogue=cat,
        signals=ProjectSignals(explicit_no_project=True),
        seal=SealRoute.UTTERANCE_FINALIZED,
    )
    print(f"open_turn {i}: {(time.monotonic() - t) * 1000:.1f} ms")
pr = cProfile.Profile()
pr.enable()
open_turn(
    engine,
    "Good evening, Val.",
    catalogue=cat,
    signals=ProjectSignals(explicit_no_project=True),
    seal=SealRoute.UTTERANCE_FINALIZED,
)
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(12)
print(s.getvalue()[:3000])
