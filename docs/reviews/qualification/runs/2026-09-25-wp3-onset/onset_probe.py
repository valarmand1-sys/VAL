"""Is the opening of an utterance preserved on its way to Whisper? — WP3 owner diagnostic §4, §5.

His diagnostic said "Good evening, Val." and the canonical transcript was "evening
Val." — three times out of three in the live store. This probe separates the two
questions the order keeps apart:

**AUDIO PRESERVATION.** A controlled fixture shaped like live Voice capture — an
already-listening microphone (a lead-in of room-level noise), then speech whose
first word begins at LOW ENERGY — is carried through the production-shaped path:

    the desktop's shipped AudioWorklet (`public/pcm-worklet.js`, run as-is)
        -> 20 ms int16 chunks, in posting order
        -> payloads coalesced the way the ordered sender may coalesce them
        -> the helper's own int16 -> float conversion
        -> the helper's own `Listener`: Silero VAD admission and speech-start pre-roll
        -> the exact array the helper hands to `whisper_full`

The helper's code is imported and run unmodified; the probe only *observes* it, by
wrapping `probabilities`, `begin` and `transcribe` to record what they were given.
So every position below is exact, in samples of the 16 kHz stream, and the content
check is an exact comparison against the fixture — not an inference from the words
that came back.

**RECOGNITION**, separately. The complete valid input — the whole utterance from
before its true onset — is given to the same unchanged Whisper Small, and its exact
text is kept. That shows what the recognizer does with complete input and nothing
more.

The speech is synthesised locally by macOS `say` and exists only in memory for the
run. **No owner audio is involved, nothing is written but this probe's JSON report,
and no model, decoding setting or prompt is changed.**

Run with the dedicated voice runtime (the only interpreter holding numpy):

    ~/.val-runtimes/voice-venv/bin/python onset_probe.py <label>
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
LIBRARY = Path.home() / ".val-runtimes" / "whisper.cpp" / "build" / "bin" / "libwhisper.dylib"
MODELS = Path.home() / ".val-models" / "whisper"
os.environ.setdefault("VAL_WHISPER_LIB", str(LIBRARY))
sys.path.insert(0, str(ROOT / "infrastructure" / "voice"))

import whisper_listen  # noqa: E402 - the production helper, imported unmodified

CAPTURE_RATE = 48_000  # what the Mac's input device delivers to the webview
RATE = 16_000
DECIMATION = CAPTURE_RATE // RATE
PHRASE = "Good evening, Val."
#: The shipped endpoint configuration, as the service passes it to the helper.
ENDPOINT = {
    "threshold": 0.5,
    "min_speech_ms": 220,
    "min_silence_ms": 650,
    "speech_pad_ms": 80,
    "max_utterance_s": 30.0,
}
LEAD_SECONDS = 1.5  # already listening: he has not started speaking yet
TAIL_SECONDS = 1.5  # silence after, so the utterance ends by endpoint
NOISE_DBFS = -60.0  # room-level noise floor, RMS
ONSET_THRESHOLD = 1e-3  # what counts as the first sample of speech in the clean take


def synthesize(voice: str) -> np.ndarray:
    """The phrase, from the local macOS voice, as float32 at the capture rate."""
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "speech.wav"
        subprocess.run(
            ["say", "-v", voice, "-o", str(target), f"--data-format=LEI16@{CAPTURE_RATE}", PHRASE],
            check=True,
        )
        with wave.open(str(target), "rb") as handle:
            assert handle.getframerate() == CAPTURE_RATE and handle.getnchannels() == 1
            frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def build(speech: np.ndarray, *, ramp_ms: float, ramp_db: float, lead: float, seed: int):
    """Lead-in noise, then speech whose first word rises from `ramp_db` to full level."""
    start = int(np.argmax(np.abs(speech) > ONSET_THRESHOLD))
    speech = speech[start:].copy()  # the clean take now begins exactly at its onset
    ramp = int(ramp_ms / 1000 * CAPTURE_RATE)
    if ramp:
        gain_db = np.linspace(ramp_db, 0.0, ramp, dtype=np.float32)
        speech[:ramp] *= 10 ** (gain_db / 20)
    lead_samples = int(round(lead * CAPTURE_RATE / DECIMATION)) * DECIMATION
    tail = int(TAIL_SECONDS * CAPTURE_RATE)
    clean = np.concatenate(
        [np.zeros(lead_samples, np.float32), speech, np.zeros(tail, np.float32)]
    )
    noise = np.random.default_rng(seed).normal(0.0, 10 ** (NOISE_DBFS / 20), clean.size)
    return (clean + noise.astype(np.float32)).astype(np.float32), lead_samples, speech.size


def worklet(capture: np.ndarray) -> tuple[bytes, dict]:
    """The shipped AudioWorklet, run as-is under node, in 128-frame render quanta."""
    completed = subprocess.run(
        ["node", str(HERE / "worklet_shim.mjs"), str(CAPTURE_RATE)],
        input=capture.astype("<f4").tobytes(),
        capture_output=True,
        check=True,
    )
    return completed.stdout, json.loads(completed.stderr.decode().strip().splitlines()[-1])


def payloads(stream: bytes, sizes: list[int]) -> list[bytes]:
    """Split the ordered chunk stream into payloads of these chunk counts, cycling."""
    out, at, index = [], 0, 0
    chunk = 320 * 2
    while at < len(stream):
        take = sizes[index % len(sizes)] * chunk
        out.append(stream[at : at + take])
        at += take
        index += 1
    return out


class Observed:
    """What the unmodified helper did, recorded from outside it."""

    def __init__(self) -> None:
        self.listener = whisper_listen.Listener(
            str(MODELS / "ggml-small.en.bin"), str(MODELS / "ggml-silero-v6.2.0.bin"), ENDPOINT
        )
        self.fed = 0  # samples handed to `feed`, i.e. the stream position
        self.windows: list[float] = []  # one max probability per 512-sample window
        self.begins: list[int] = []  # stream index of the window that admitted speech
        self.inputs: list[tuple[str, np.ndarray]] = []
        self.events: list[dict] = []
        listener = self.listener
        probabilities = listener.probabilities
        begin = listener.begin
        transcribe = listener.transcribe
        finalize = listener.finalize
        self._finalizing = False

        def observed_probabilities(window):
            probs = probabilities(window)
            self.windows.append(max(probs) if probs else 0.0)
            return probs

        def observed_begin():
            self.begins.append(len(self.windows) - 1)
            return begin()

        def observed_transcribe(samples):
            self.inputs.append(("final" if self._finalizing else "provisional", samples.copy()))
            return transcribe(samples)

        def observed_finalize(reason):
            self._finalizing = True
            try:
                return finalize(reason)
            finally:
                self._finalizing = False

        listener.probabilities = observed_probabilities
        listener.begin = observed_begin
        listener.transcribe = observed_transcribe
        listener.finalize = observed_finalize
        whisper_listen.emit = lambda **payload: self.events.append(payload)

    def feed(self, payload: bytes) -> None:
        samples = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.0
        self.fed += samples.size
        self.listener.feed(samples)

    def close(self) -> None:
        self.listener.close()


def locate(stream: np.ndarray, piece: np.ndarray) -> int:
    """Where `piece` sits in `stream`, exactly; -1 if it is not a contiguous slice."""
    probe = piece[:64]
    candidates = np.flatnonzero(stream[: stream.size - probe.size + 1] == probe[0])
    for index in candidates:
        if np.array_equal(stream[index : index + piece.size], piece):
            return int(index)
    return -1


def run_case(name: str, speech: np.ndarray, *, ramp_ms: float, ramp_db: float, lead: float,
             splits: list[list[int]], seed: int = 7) -> dict:
    capture, lead48, speech48 = build(speech, ramp_ms=ramp_ms, ramp_db=ramp_db, lead=lead, seed=seed)
    raw, shim = worklet(capture)
    onset = lead48 // DECIMATION  # the true onset, in the 16 kHz stream
    stream = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    ms = lambda samples: round(samples / RATE * 1000, 1)  # noqa: E731

    per_split = []
    for sizes in splits:
        observed = Observed()
        started = time.monotonic()
        for payload in payloads(raw, sizes):
            observed.feed(payload)
        observed.close()
        finals = [array for kind, array in observed.inputs if kind == "final"]
        texts = [event.get("text", "") for event in observed.events if event.get("event") == "final"]
        confident = [i for i, p in enumerate(observed.windows) if p >= ENDPOINT["threshold"]]
        first_confident = next((i for i in confident if (i + 1) * 512 > onset), None)
        record = {
            "payload_chunk_counts": sizes,
            "samples_fed": observed.fed,
            "windows": len(observed.windows),
            "utterances_finalized": len(finals),
            "elapsed_s": round(time.monotonic() - started, 3),
        }
        if finals:
            final = finals[0]
            first = locate(stream, final)
            admit = observed.begins[0]
            record.update(
                {
                    "first_confident_window_start": None if first_confident is None else first_confident * 512,
                    "true_onset_to_first_confident_window_ms": None
                    if first_confident is None
                    else ms(first_confident * 512 - onset),
                    "admission_window_end": (admit + 1) * 512,
                    "true_onset_to_admission_ms": ms((admit + 1) * 512 - onset),
                    "recognizer_input_first_sample": first,
                    "recognizer_input_samples": int(final.size),
                    "recognizer_input_ms": ms(final.size),
                    "recognizer_input_is_contiguous_slice_of_stream": first >= 0,
                    "recognizer_input_sha256": hashlib.sha256(final.tobytes()).hexdigest(),
                    "opening_audio_lost_ms": ms(max(0, first - onset)) if first >= 0 else None,
                    "pre_roll_before_true_onset_ms": ms(max(0, onset - first)) if first >= 0 else None,
                    "whisper_final_text": texts[0] if texts else None,
                }
            )
        per_split.append(record)

    # RECOGNITION, separately: the complete valid input — from the configured pad
    # before the true onset to the end of the speech — through the same unchanged
    # Whisper Small. What the recognizer does with input that is known to be whole.
    pad = int(ENDPOINT["speech_pad_ms"] / 1000 * RATE)
    complete = stream[max(0, onset - pad) : onset + speech48 // DECIMATION + pad]
    listener = whisper_listen.Listener(
        str(MODELS / "ggml-small.en.bin"), str(MODELS / "ggml-silero-v6.2.0.bin"), ENDPOINT
    )
    try:
        complete_text = listener.transcribe(complete)
    finally:
        listener.close()

    identical = len({split.get("recognizer_input_sha256") for split in per_split}) == 1
    return {
        "case": name,
        "fixture": {
            "lead_in_ms": round(lead48 / CAPTURE_RATE * 1000, 1),
            "noise_dbfs_rms": NOISE_DBFS,
            "first_word_onset_ramp_ms": ramp_ms,
            "first_word_onset_start_db": ramp_db if ramp_ms else 0.0,
            "speech_ms": round(speech48 / CAPTURE_RATE * 1000, 1),
            "true_onset_sample_16k": onset,
        },
        "worklet": {
            **shim,
            "expected_output_samples": (capture.size // DECIMATION) // 320 * 320,
            "continuous": shim["output_samples"] == (capture.size // DECIMATION) // 320 * 320,
        },
        "splits": per_split,
        "recognizer_input_identical_across_payload_splits": identical,
        "complete_valid_input": {
            "first_sample": max(0, onset - pad),
            "samples": int(complete.size),
            "unchanged_whisper_small_text": complete_text,
        },
    }


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    helper = (ROOT / "infrastructure/voice/whisper_listen.py").read_bytes()
    report = {
        "label": label,
        "phrase": PHRASE,
        "helper_sha256": hashlib.sha256(helper).hexdigest(),
        "endpoint": ENDPOINT,
        "macos": platform.mac_ver()[0],
        "cases": [],
    }
    splits = [[1], [4, 1, 7, 2], [50]]  # every chunk alone, uneven coalescing, 1 s payloads
    for voice in ("Daniel", "Samantha"):
        speech = synthesize(voice)
        report["cases"].append(
            run_case(f"{voice}: already listening, low-energy onset", speech,
                     ramp_ms=150, ramp_db=-24, lead=LEAD_SECONDS, splits=splits)
        )
        report["cases"].append(
            run_case(f"{voice}: already listening, natural onset", speech,
                     ramp_ms=0, ramp_db=0, lead=LEAD_SECONDS, splits=splits[:1])
        )
        report["cases"].append(
            run_case(f"{voice}: speech from capture sample zero", speech,
                     ramp_ms=150, ramp_db=-24, lead=0.0, splits=splits[:1])
        )
    out = HERE / f"onset-probe-{label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    for case in report["cases"]:
        first = case["splits"][0]
        print(
            f"{case['case']}: onset->first confident "
            f"{first.get('true_onset_to_first_confident_window_ms')} ms, "
            f"onset->admission {first.get('true_onset_to_admission_ms')} ms, "
            f"lost {first.get('opening_audio_lost_ms')} ms, "
            f"final {first.get('whisper_final_text')!r}; "
            f"complete input -> {case['complete_valid_input']['unchanged_whisper_small_text']!r}"
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
