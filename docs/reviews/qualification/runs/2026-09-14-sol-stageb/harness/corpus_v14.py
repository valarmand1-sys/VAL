"""Packet corpus v1.4 — v1.3 with I4 replaced and nothing else (approved and frozen 9 September 2026)."""
from corpus_v13 import *  # noqa: F401,F403
from corpus_v13 import INSTRUCTION as _I13, corpus_document as _doc13
INSTRUCTION = dict(_I13)
INSTRUCTION["I4"] = ('For this fictional exercise, use only these facts: the lead actor is unavailable Tuesday morning; '
                     'the supporting actor is unavailable Wednesday; the harbour exterior is scheduled for Friday; heavy rain is '
                     'expected Friday. Give the schedule risks under exactly two headings, "Cast" and "Weather", and nothing else.')
def corpus_document() -> dict:
    d = _doc13(); d["version"] = "v1.4"; d["instruction"] = dict(INSTRUCTION); return d
