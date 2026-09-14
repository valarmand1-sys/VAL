"""Packet corpus v1.6 — v1.5 with exactly the two ruled repairs (9 September 2026): O6 replaced;
O9's prompt unchanged with its criterion amended in the packet. Nothing else."""
from corpus_v15 import *  # noqa: F401,F403
from corpus_v15 import ORDINARY as _O15, corpus_document as _doc15
ORDINARY = dict(_O15)
ORDINARY["O6"] = ("For this fictional exercise, use only these facts: Thursday's read-through is at ten in the Fenwick Room; "
                  "the revised pages for act two arrive on Wednesday night; two of the principals are on set at the harbour, "
                  "three hours away, until nine on Thursday morning. Give me the three risks to Thursday's read, one line each, and nothing else.")
def corpus_document() -> dict:
    d = _doc15(); d["version"] = "v1.6"; d["ordinary"] = dict(ORDINARY); return d
