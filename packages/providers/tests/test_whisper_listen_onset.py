"""The opening of an utterance reaches Whisper — owner diagnostic, 25 September 2026.

He said "Good evening, Val." and the canonical transcript was "evening Val.", three
times in three. A controlled fixture carried through the shipped worklet and the
unmodified helper showed why: while it waited for enough confident windows to admit
speech, the helper kept only the last `speech_pad_ms` of *everything*, the confident
run included, so the first 148 to 240 ms of speech the VAD was already sure of was
discarded before Whisper ever saw it (`docs/reviews/qualification/runs/
2026-09-25-wp3-onset/`). The same unchanged Whisper Small, given the whole
utterance, heard "Good".

These tests drive the helper's own endpoint machine — `whisper_listen.Listener`,
imported from the file production runs — with scripted VAD decisions, and check the
exact array it hands the recognizer against the stream it was fed. Content is
checked sample for sample, not inferred from any words.

**They run in the dedicated voice runtime**, the only interpreter holding numpy,
and are skipped where it is absent — which includes CI. Adding numpy to the
production environment to run them there is exactly what the standing instruction
forbids; the fixture probe's JSON reports are the retained evidence alongside.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER_DIR = ROOT / "infrastructure" / "voice"
VOICE_PYTHON = Path.home() / ".val-runtimes" / "voice-venv" / "bin" / "python"

pytestmark = pytest.mark.skipif(
    not VOICE_PYTHON.exists(),
    reason="the dedicated voice runtime is not installed here (it never is in CI)",
)

#: Runs inside the voice runtime. Each window's samples all carry its own index, so
#: any sample of the recognizer's input says exactly which window it came from.
SCENARIOS = r"""
import json, sys
import numpy as np
sys.path.insert(0, sys.argv[1])
import whisper_listen as wl

ENDPOINT = {"threshold": 0.5, "min_speech_ms": 220, "min_silence_ms": 650,
            "speech_pad_ms": 80, "max_utterance_s": 30.0}
W = wl.VAD_WINDOW

class Stub:
    def whisper_vad_reset_state(self, vad):
        pass

def listener(decisions):
    events, inputs = [], []
    wl.emit = lambda **payload: events.append(payload)
    item = wl.Listener.__new__(wl.Listener)
    item.configure(ENDPOINT)
    item.lib, item.vad = Stub(), None
    item.probabilities = lambda window: [decisions[int(round(window[0] * 1e4))]]
    item.transcribe = lambda samples: inputs.append(samples.copy()) or ""
    return item, events, inputs

def stream(count):
    return np.concatenate([np.full(W, k / 1e4, dtype=np.float32) for k in range(count)])

def run(decisions, splits):
    audio = stream(len(decisions))
    item, events, inputs = listener(decisions)
    at, index = 0, 0
    while at < audio.size:
        size = splits[index % len(splits)]
        item.feed(audio[at:at + size]); at += size; index += 1
    finals = [e for e in events if e.get("event") == "speech_end"]
    starts = [e for e in events if e.get("event") == "speech_start"]
    final_inputs = inputs[-len(finals):] if finals else []
    out = []
    for end, start, given in zip(finals, starts, final_inputs):
        first = end["first_sample"]
        out.append({
            "first_sample": first,
            "samples": end["samples"],
            "matches_stream": bool(np.array_equal(given, audio[first:first + given.size])),
            "given_size": int(given.size),
            "run_start_sample": start["run_start_sample"],
            "admitted_sample": start["admitted_sample"],
            "silence_seconds": end["silence_seconds"],
            "voiced_seconds": end["voiced_seconds"],
            "received_samples": end["received_samples"],
        })
    return {"fed": int(audio.size), "utterances": out}

def speech(lead, soft, loud, tail, soft_p=0.3):
    return [0.0] * lead + [soft_p] * soft + [0.9] * loud + [0.0] * tail

result = {
    # Already listening: 40 quiet windows, two low-energy onset windows the VAD is not
    # yet sure of, then confident speech, then enough silence to end it.
    "listening": run(speech(40, 2, 20, 25), [320]),
    "listening_coalesced": run(speech(40, 2, 20, 25), [1280, 320, 2240, 640, 16000]),
    # A confident blip too short to admit, a gap, then real speech.
    "blip_then_speech": run([0.0] * 20 + [0.9] * 3 + [0.0] + [0.9] * 20 + [0.0] * 25, [320]),
    # Speech from the very first sample the helper receives.
    "sample_zero": run([0.9] * 20 + [0.0] * 25, [320]),
}
print(json.dumps(result))
"""


def scenarios() -> dict:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed script
        [str(VOICE_PYTHON), "-c", SCENARIOS, str(HELPER_DIR)],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


WINDOW = 512
PAD = 1280  # 80 ms at 16 kHz, the governed speech_pad_ms


@pytest.fixture(scope="module")
def results() -> dict:
    return scenarios()


def test_the_utterance_starts_one_pad_before_its_first_confident_window(results: dict) -> None:
    utterance = results["listening"]["utterances"][0]
    first_confident = 42 * WINDOW
    assert utterance["run_start_sample"] == first_confident
    # Before the repair this was `admitted_sample - PAD`: 144 ms of confident speech
    # later, and the opening word with it.
    assert utterance["first_sample"] == first_confident - PAD
    assert utterance["admitted_sample"] - first_confident == 7 * WINDOW  # 224 ms to admit


def test_the_low_energy_onset_before_vad_confidence_is_inside_the_pre_roll(results: dict) -> None:
    utterance = results["listening"]["utterances"][0]
    true_onset = 40 * WINDOW  # the two soft windows begin here
    offset = utterance["run_start_sample"] - true_onset
    assert offset == 2 * WINDOW  # 64 ms of speech before the VAD was sure of it
    assert offset <= PAD  # and the governed pad covers it
    assert utterance["first_sample"] <= true_onset


def test_what_whisper_receives_is_the_stream_itself_without_a_gap(results: dict) -> None:
    for case in ("listening", "listening_coalesced", "blip_then_speech", "sample_zero"):
        utterance = results[case]["utterances"][0]
        assert utterance["matches_stream"], case
        assert utterance["given_size"] == utterance["samples"], case
        assert utterance["received_samples"] <= results[case]["fed"], case


def test_payload_boundaries_do_not_change_what_whisper_receives(results: dict) -> None:
    one = results["listening"]["utterances"][0]
    other = results["listening_coalesced"]["utterances"][0]
    assert (one["first_sample"], one["samples"]) == (other["first_sample"], other["samples"])


def test_a_run_too_short_to_admit_becomes_context_not_a_hole(results: dict) -> None:
    utterance = results["blip_then_speech"]["utterances"][0]
    assert utterance["run_start_sample"] == 24 * WINDOW
    assert utterance["first_sample"] == 24 * WINDOW - PAD
    assert utterance["matches_stream"]


def test_speech_from_capture_sample_zero_loses_nothing(results: dict) -> None:
    utterance = results["sample_zero"]["utterances"][0]
    assert utterance["first_sample"] == 0
    assert utterance["run_start_sample"] == 0


def test_the_silence_that_ended_it_is_reported_rather_than_zero(results: dict) -> None:
    utterance = results["listening"]["utterances"][0]
    # 650 ms at 32 ms a window is the 21st silent window: 0.672 s. The first version
    # read this after clearing it and reported 0.000 s for all three of his runs.
    assert utterance["silence_seconds"] == pytest.approx(21 * 0.032, abs=1e-3)
    # The admitting run is speech the VAD was sure of, and now counts as voiced.
    assert utterance["voiced_seconds"] == pytest.approx(20 * 0.032, abs=1e-3)
