"""Live speech recognition, inside the house's dedicated voice runtime.

Owner execution order, Voice mode work package 1. This file is executed by
`~/.val-runtimes/voice-venv/bin/python`, a **dedicated** interpreter holding
nothing but numpy. whisper.cpp is reached through `ctypes` against the shared
library built from the pinned release, so **nothing is added to Val's production
Python dependency set**.

**It imports nothing from Val.** Framed records arrive on stdin and JSON lines
leave on stdout. Nothing reaches it through the command line except one
configuration object, so no value from a model, a document or a tool result can
become an argument.

**It owns no microphone.** whisper.cpp's SDL demonstration program is neither
built nor used; Val's service captures audio elsewhere and hands it here as PCM.
Audio lives in a volatile array for exactly as long as endpointing and
transcription need it, and is dropped the moment an utterance is settled.
**There is no file write anywhere in this module** — that is what makes live
audio ephemeral rather than merely uncollected.

The protocol, deliberately small:

    stdin   [u32 kind][u32 length][payload]
            kind 0 — `length` bytes of little-endian int16 mono PCM at 16 kHz
            kind 1 — a JSON control object

    stdout  one JSON object per line: ready, speech_start, provisional,
            speech_end, final, error

Two recognition states, never confused: **provisional** is a rolling guess over
speech still in progress, and **final** is the settled transcription of a
completed utterance. Only final text ever becomes a conversation turn, and that
decision is made above this file, not here.
"""

from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import time
from collections.abc import Iterator
from ctypes import c_bool, c_char_p, c_float, c_int, c_size_t, c_void_p
from typing import BinaryIO

import numpy as np

#: The pinned build, carried in `ready` so the record can name the exact
#: recognizer that produced every transcript.
WHISPER_VERSION = "v1.9.4"
WHISPER_COMMIT = "927cfce34f31707e17f2bff35c349632fb9e2c3a"
LIBRARY = os.environ.get(
    "VAL_WHISPER_LIB",
    os.path.expanduser("~/.val-runtimes/whisper.cpp/build/bin/libwhisper.dylib"),
)

#: Everything downstream assumes this rate; the capture path resamples to it.
SAMPLE_RATE = 16_000
#: Silero consumes 512-sample windows at 16 kHz — one probability per 32 ms.
VAD_WINDOW = 512

#: How often a rolling provisional decode may run while speech continues, and
#: how much speech must exist first.
#:
#: Measured in **audio time, not wall-clock time**. In live use the two are the
#: same, because speech arrives as it is spoken. They diverge when audio is fed
#: faster than real time — a test, or the integration fixture — and wall-clock
#: gating there silently produces no provisional events at all, which would make
#: the rolling guess untestable and the interval unprovable. Audio time gives the
#: same live behaviour and a deterministic one.
PROVISIONAL_EVERY_MS = 700
PROVISIONAL_MIN_SPEECH_MS = 400


class WhisperAhead(ctypes.Structure):
    _fields_ = [("n_text_layer", c_int), ("n_head", c_int)]


class WhisperAheads(ctypes.Structure):
    _fields_ = [("n_heads", c_size_t), ("heads", ctypes.POINTER(WhisperAhead))]


class WhisperContextParams(ctypes.Structure):
    _fields_ = [
        ("use_gpu", c_bool),
        ("flash_attn", c_bool),
        ("gpu_device", c_int),
        ("dtw_token_timestamps", c_bool),
        ("dtw_aheads_preset", c_int),
        ("dtw_n_top", c_int),
        ("dtw_aheads", WhisperAheads),
        ("dtw_mem_size", c_size_t),
    ]


class WhisperVadParams(ctypes.Structure):
    _fields_ = [
        ("threshold", c_float),
        ("min_speech_duration_ms", c_int),
        ("min_silence_duration_ms", c_int),
        ("max_speech_duration_s", c_float),
        ("speech_pad_ms", c_int),
        ("samples_overlap", c_float),
    ]


class WhisperVadContextParams(ctypes.Structure):
    _fields_ = [("n_threads", c_int), ("use_gpu", c_bool), ("gpu_device", c_int)]


class _Greedy(ctypes.Structure):
    _fields_ = [("best_of", c_int)]


class _BeamSearch(ctypes.Structure):
    _fields_ = [("beam_size", c_int), ("patience", c_float)]


class WhisperFullParams(ctypes.Structure):
    """`whisper_full_params` of the pinned release, field for field.

    The struct is obtained from the library's own
    `whisper_full_default_params` and then mutated, rather than constructed
    here: the defaults are the library's business and only the handful of fields
    this house chooses are written. The layout is verified at startup against
    those defaults, because a wrong ctypes layout does not fail loudly on its
    own — it silently reads and writes the wrong bytes.
    """

    _fields_ = [
        ("strategy", c_int),
        ("n_threads", c_int),
        ("n_max_text_ctx", c_int),
        ("offset_ms", c_int),
        ("duration_ms", c_int),
        ("translate", c_bool),
        ("no_context", c_bool),
        ("no_timestamps", c_bool),
        ("single_segment", c_bool),
        ("print_special", c_bool),
        ("print_progress", c_bool),
        ("print_realtime", c_bool),
        ("print_timestamps", c_bool),
        ("token_timestamps", c_bool),
        ("thold_pt", c_float),
        ("thold_ptsum", c_float),
        ("max_len", c_int),
        ("split_on_word", c_bool),
        ("max_tokens", c_int),
        ("debug_mode", c_bool),
        ("audio_ctx", c_int),
        ("tdrz_enable", c_bool),
        ("suppress_regex", c_char_p),
        ("initial_prompt", c_char_p),
        ("carry_initial_prompt", c_bool),
        ("prompt_tokens", c_void_p),
        ("prompt_n_tokens", c_int),
        ("language", c_char_p),
        ("detect_language", c_bool),
        ("suppress_blank", c_bool),
        ("suppress_nst", c_bool),
        ("temperature", c_float),
        ("max_initial_ts", c_float),
        ("length_penalty", c_float),
        ("temperature_inc", c_float),
        ("entropy_thold", c_float),
        ("logprob_thold", c_float),
        ("no_speech_thold", c_float),
        ("greedy", _Greedy),
        ("beam_search", _BeamSearch),
        ("new_segment_callback", c_void_p),
        ("new_segment_callback_user_data", c_void_p),
        ("progress_callback", c_void_p),
        ("progress_callback_user_data", c_void_p),
        ("encoder_begin_callback", c_void_p),
        ("encoder_begin_callback_user_data", c_void_p),
        ("abort_callback", c_void_p),
        ("abort_callback_user_data", c_void_p),
        ("logits_filter_callback", c_void_p),
        ("logits_filter_callback_user_data", c_void_p),
        ("grammar_rules", c_void_p),
        ("n_grammar_rules", c_size_t),
        ("i_start_rule", c_size_t),
        ("grammar_penalty", c_float),
        ("vad", c_bool),
        ("vad_model_path", c_char_p),
        ("vad_params", WhisperVadParams),
    ]


def emit(**payload: object) -> None:
    """One JSON line on stdout, flushed. The only way anything leaves here."""
    json.dump(payload, sys.stdout, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


def bind(library: str) -> ctypes.CDLL:
    lib = ctypes.CDLL(library)
    lib.whisper_context_default_params.restype = WhisperContextParams
    lib.whisper_init_from_file_with_params.argtypes = [c_char_p, WhisperContextParams]
    lib.whisper_init_from_file_with_params.restype = c_void_p
    lib.whisper_full_default_params.argtypes = [c_int]
    lib.whisper_full_default_params.restype = WhisperFullParams
    lib.whisper_full.argtypes = [c_void_p, WhisperFullParams, ctypes.POINTER(c_float), c_int]
    lib.whisper_full.restype = c_int
    lib.whisper_full_n_segments.argtypes = [c_void_p]
    lib.whisper_full_n_segments.restype = c_int
    lib.whisper_full_get_segment_text.argtypes = [c_void_p, c_int]
    lib.whisper_full_get_segment_text.restype = c_char_p
    lib.whisper_free.argtypes = [c_void_p]

    lib.whisper_vad_default_context_params.restype = WhisperVadContextParams
    lib.whisper_vad_init_from_file_with_params.argtypes = [c_char_p, WhisperVadContextParams]
    lib.whisper_vad_init_from_file_with_params.restype = c_void_p
    lib.whisper_vad_detect_speech_no_reset.argtypes = [c_void_p, ctypes.POINTER(c_float), c_int]
    lib.whisper_vad_detect_speech_no_reset.restype = c_bool
    lib.whisper_vad_reset_state.argtypes = [c_void_p]
    lib.whisper_vad_n_probs.argtypes = [c_void_p]
    lib.whisper_vad_n_probs.restype = c_int
    lib.whisper_vad_probs.argtypes = [c_void_p]
    lib.whisper_vad_probs.restype = ctypes.POINTER(c_float)
    lib.whisper_vad_free.argtypes = [c_void_p]
    return lib


def verify_layout(params: WhisperFullParams) -> None:
    """Prove the struct binding matches this library before anything runs.

    The library's own defaults are checked at fields spread across the whole
    struct: if the offsets are right these are the documented values, and if
    they are not, execution stops here rather than corrupting memory quietly.
    """
    problems = []
    if not 1 <= params.n_threads <= 64:
        problems.append(f"n_threads={params.n_threads}")
    if params.n_max_text_ctx not in (16384, 224):
        problems.append(f"n_max_text_ctx={params.n_max_text_ctx}")
    if params.language not in (b"en", b"auto", None):
        problems.append(f"language={params.language!r}")
    if not -1.5 <= params.logprob_thold <= 0.0:
        problems.append(f"logprob_thold={params.logprob_thold}")
    if not 0.0 <= params.no_speech_thold <= 1.0:
        problems.append(f"no_speech_thold={params.no_speech_thold}")
    if not 0 <= params.greedy.best_of <= 16:
        problems.append(f"greedy.best_of={params.greedy.best_of}")
    if params.vad is not False:
        problems.append(f"vad={params.vad}")
    if problems:
        raise RuntimeError(
            "the whisper_full_params binding does not match this library: " + ", ".join(problems)
        )


class Listener:
    """One live voice session: PCM in, speech boundaries and text out."""

    def __init__(self, model: str, vad_model: str, endpoint: dict[str, float]) -> None:
        self.lib = bind(LIBRARY)
        context_params = self.lib.whisper_context_default_params()
        context_params.use_gpu = True
        self.ctx = self.lib.whisper_init_from_file_with_params(model.encode(), context_params)
        if not self.ctx:
            raise RuntimeError(f"the ASR model could not be loaded from {model}")
        vad_context = self.lib.whisper_vad_default_context_params()
        # **Required, not preferred.** `use_gpu = True` aborts the process in this
        # build: the Silero graph has a pre-allocated tensor in an MTL buffer that
        # cannot run the operation, and ggml calls `abort()` rather than falling
        # back. Measured here, the CPU path costs 0.028 s for 11 s of audio — a
        # real-time factor of 0.003 — so nothing is given up by it.
        vad_context.use_gpu = False
        self.vad = self.lib.whisper_vad_init_from_file_with_params(vad_model.encode(), vad_context)
        if not self.vad:
            raise RuntimeError(f"the VAD model could not be loaded from {vad_model}")

        self.params = self.lib.whisper_full_default_params(0)  # greedy
        verify_layout(self.params)
        self.params.print_progress = False
        self.params.print_realtime = False
        self.params.print_timestamps = False
        self.params.print_special = False
        self.params.no_timestamps = True
        self.params.translate = False
        self.params.language = b"en"
        self.params.n_threads = min(8, os.cpu_count() or 4)
        # Each utterance is decoded on its own. A live turn must never inherit
        # the previous turn's text as a prompt, or one misrecognition becomes
        # self-reinforcing across a whole conversation.
        self.params.no_context = True
        self.params.suppress_blank = True
        self.params.suppress_nst = True

        self.threshold = float(endpoint["threshold"])
        self.min_speech = float(endpoint["min_speech_ms"]) / 1000.0
        self.min_silence = float(endpoint["min_silence_ms"]) / 1000.0
        self.pad = float(endpoint["speech_pad_ms"]) / 1000.0
        self.max_utterance = float(endpoint["max_utterance_s"])

        self.pending = np.zeros(0, dtype=np.float32)  # not yet windowed
        self.utterance = np.zeros(0, dtype=np.float32)  # the live utterance
        self.padding = np.zeros(0, dtype=np.float32)  # pre-speech padding ring
        self.in_speech = False
        self.speech_run = 0.0
        self.silence_run = 0.0
        self.utterances = 0
        #: Samples of this utterance already covered by a provisional decode, and
        #: what the last one cost. The cost is what keeps a long utterance from
        #: spending more time guessing than listening.
        self.provisional_at = 0
        self.provisional_cost_ms = 0.0

    # --- recognition ---------------------------------------------------------------

    def transcribe(self, samples: np.ndarray) -> str:
        if samples.size < SAMPLE_RATE // 10:
            return ""
        buffer = (c_float * samples.size).from_buffer_copy(samples.tobytes())
        if self.lib.whisper_full(self.ctx, self.params, buffer, samples.size) != 0:
            raise RuntimeError("whisper_full failed on this utterance")
        pieces = []
        for index in range(self.lib.whisper_full_n_segments(self.ctx)):
            text = self.lib.whisper_full_get_segment_text(self.ctx, index)
            if text:
                pieces.append(text.decode("utf-8", "replace"))
        return "".join(pieces).strip()

    def probabilities(self, window: np.ndarray) -> list[float]:
        buffer = (c_float * window.size).from_buffer_copy(window.tobytes())
        if not self.lib.whisper_vad_detect_speech_no_reset(self.vad, buffer, window.size):
            return []
        count = self.lib.whisper_vad_n_probs(self.vad)
        if count <= 0:
            return []
        probs = self.lib.whisper_vad_probs(self.vad)
        return [float(probs[index]) for index in range(count)]

    # --- the live loop -------------------------------------------------------------

    def feed(self, samples: np.ndarray) -> None:
        """One block of PCM, advanced through the endpoint machine."""
        self.pending = np.concatenate([self.pending, samples])
        per_window = VAD_WINDOW / SAMPLE_RATE

        while self.pending.size >= VAD_WINDOW:
            window, self.pending = self.pending[:VAD_WINDOW], self.pending[VAD_WINDOW:]
            probs = self.probabilities(window)
            speaking = bool(probs) and max(probs) >= self.threshold

            if self.in_speech:
                self.utterance = np.concatenate([self.utterance, window])
                if speaking:
                    self.silence_run = 0.0
                else:
                    self.silence_run += per_window
                    if self.silence_run >= self.min_silence:
                        self.finalize("silence")
                        continue
                if self.utterance.size / SAMPLE_RATE >= self.max_utterance:
                    self.finalize("maximum_length")
                    continue
                self.maybe_provisional()
            else:
                # Keep only the padding the configuration asks for, so an
                # utterance starts a little before its first confident frame.
                keep = int(self.pad * SAMPLE_RATE)
                self.padding = np.concatenate([self.padding, window])[-keep:] if keep else window
                if speaking:
                    self.speech_run += per_window
                    if self.speech_run >= self.min_speech:
                        self.begin()
                else:
                    self.speech_run = 0.0

    def begin(self) -> None:
        self.in_speech = True
        self.silence_run = 0.0
        self.utterances += 1
        self.utterance = np.concatenate([self.padding, self.utterance])
        self.padding = np.zeros(0, dtype=np.float32)
        self.provisional_at = 0
        self.provisional_cost_ms = 0.0
        emit(event="speech_start", session=self.utterances, at=time.monotonic())

    def maybe_provisional(self) -> None:
        spoken_ms = self.utterance.size / SAMPLE_RATE * 1000
        if spoken_ms < PROVISIONAL_MIN_SPEECH_MS:
            return
        # At most one guess per interval of speech — and never more often than
        # twice the last guess's own cost, so a long utterance on a slow machine
        # spends most of its time listening rather than re-guessing.
        interval = max(PROVISIONAL_EVERY_MS, 2 * self.provisional_cost_ms)
        if spoken_ms - self.provisional_at / SAMPLE_RATE * 1000 < interval:
            return
        self.provisional_at = self.utterance.size
        started = time.monotonic()
        try:
            text = self.transcribe(self.utterance)
        except RuntimeError:
            return
        finally:
            self.provisional_cost_ms = (time.monotonic() - started) * 1000
        if text:
            emit(event="provisional", session=self.utterances, text=text, at=time.monotonic())

    def finalize(self, reason: str) -> None:
        """Settle the utterance, report it, and release the audio at once."""
        audio, self.utterance = self.utterance, np.zeros(0, dtype=np.float32)
        self.in_speech = False
        self.speech_run = 0.0
        self.silence_run = 0.0
        self.padding = np.zeros(0, dtype=np.float32)
        endpoint_at = time.monotonic()
        emit(
            event="speech_end",
            session=self.utterances,
            reason=reason,
            at=endpoint_at,
            seconds=round(audio.size / SAMPLE_RATE, 3),
        )
        text = ""
        try:
            text = self.transcribe(audio)
        except RuntimeError as failure:
            emit(event="error", session=self.utterances, detail=str(failure))
        finally:
            # The samples are dropped here, before anything else happens. Live
            # microphone audio being ephemeral is this line, not a policy note.
            del audio
            self.lib.whisper_vad_reset_state(self.vad)
        emit(
            event="final",
            session=self.utterances,
            text=text,
            reason=reason,
            endpoint_at=endpoint_at,
            at=time.monotonic(),
        )

    def reset(self) -> None:
        self.utterance = np.zeros(0, dtype=np.float32)
        self.pending = np.zeros(0, dtype=np.float32)
        self.padding = np.zeros(0, dtype=np.float32)
        self.in_speech = False
        self.speech_run = 0.0
        self.silence_run = 0.0
        self.lib.whisper_vad_reset_state(self.vad)

    def close(self) -> None:
        self.lib.whisper_free(self.ctx)
        self.lib.whisper_vad_free(self.vad)


def records(stream: BinaryIO) -> Iterator[tuple[int, bytes]]:
    """`[u32 kind][u32 length][payload]` records off a binary stream."""
    read = stream.read
    while True:
        header = read(8)
        if not header or len(header) < 8:
            return
        kind, length = struct.unpack("<II", header)
        payload = read(length) if length else b""
        if length and (payload is None or len(payload) < length):
            return
        yield kind, payload


def main() -> int:
    configuration = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    model = configuration["model"]
    vad_model = configuration["vad_model"]
    endpoint = configuration["endpoint"]

    started = time.monotonic()
    try:
        listener = Listener(model, vad_model, endpoint)
    except (RuntimeError, OSError) as failure:
        emit(event="error", fatal=True, detail=f"{type(failure).__name__}: {failure}")
        return 1
    emit(
        event="ready",
        recognizer="whisper.cpp",
        version=WHISPER_VERSION,
        commit=WHISPER_COMMIT,
        sample_rate=SAMPLE_RATE,
        endpoint=endpoint,
        load_seconds=round(time.monotonic() - started, 3),
    )

    try:
        for kind, payload in records(sys.stdin.buffer):
            if kind == 0:
                samples = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.0
                listener.feed(samples)
            elif kind == 1:
                action = json.loads(payload).get("action")
                if action == "flush":
                    if listener.in_speech:
                        listener.finalize("flush")
                elif action == "reset":
                    listener.reset()
                elif action == "stop":
                    break
    finally:
        listener.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    # The boundary is a process: it reports rather than crashing into a
    # traceback the caller would have to parse.
    except Exception as failure:
        emit(event="error", fatal=True, detail=f"{type(failure).__name__}: {failure}")
        raise SystemExit(1) from failure
