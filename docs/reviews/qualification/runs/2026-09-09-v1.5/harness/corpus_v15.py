"""Packet corpus v1.5 — v1.4 unchanged in substance; re-versioned to bind persona v1.4 (frozen 9 September 2026)."""
from corpus_v14 import *  # noqa: F401,F403
from corpus_v14 import corpus_document as _doc14
def corpus_document() -> dict:
    d = _doc14(); d["version"] = "v1.5"; return d
