// Val's playback processor — owner order, 26 September 2026 (audio regression §8).
//
// **One continuous output, not one buffer per piece.** Streamed speech arrives as
// ~1-second WAV pieces. The previous player decoded each piece with
// `decodeAudioData` — which resamples each piece independently to the context's rate
// — and scheduled it as its own source node, so every seam was a resampler restart
// and a scheduling boundary. This processor instead receives the decoded samples of
// every piece, in order, and writes them to the device as one uninterrupted signal:
// a segment's pieces are joined sample to sample, and if the device runs at another
// rate than the speech (24 kHz), the resampler's state carries across pieces.
//
// It also owns the physical boundaries the record needs. `started` is posted when a
// segment's first sample is written to the output — sound at the device, not an
// intention to schedule — `completed` when its last sample has been, and `underrun`
// when the next piece of a segment had not arrived by the time the previous one ran
// out (silence is written; nothing is invented).
//
// Served from the application's own origin, like the microphone worklet, so the
// desktop's `default-src 'self'` policy permits it unchanged.
class ValPlaybackProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const settings = (options && options.processorOptions) || {};
    this.sourceRate = settings.sourceRate || 24000;
    //: Source samples advanced per output sample. 1 when the context runs at the
    //: speech rate, which the player asks for; otherwise linear interpolation.
    this.step = this.sourceRate / sampleRate;
    this.queue = [];
    this.piece = null;
    this.position = 0;
    //: The last source sample emitted, so interpolation crosses piece boundaries.
    this.previous = 0;
    //: The segment whose pieces are still arriving, and silence written while
    //: waiting for the next one.
    this.open = null;
    this.underrunFrames = 0;
    this.started = new Set();
    this.stopped = false;
    this.port.onmessage = (event) => this.receive(event.data);
  }

  receive(message) {
    if (message.type === "piece") {
      if (this.stopped) return;
      this.queue.push({
        key: message.key,
        samples: new Float32Array(message.samples),
        last: Boolean(message.last),
      });
    } else if (message.type === "stop") {
      this.stopped = true;
      this.queue = [];
      this.piece = null;
      this.open = null;
      this.port.postMessage({ type: "stopped" });
    }
  }

  /** Take the next piece, if one is waiting. */
  advance() {
    const next = this.queue.shift();
    if (next === undefined) {
      this.piece = null;
      return false;
    }
    if (this.open !== null && this.underrunFrames > 0 && next.key === this.open) {
      this.port.postMessage({ type: "underrun", key: this.open, frames: this.underrunFrames });
    }
    this.underrunFrames = 0;
    this.piece = next;
    if (!this.started.has(next.key) && next.samples.length > 0) {
      this.started.add(next.key);
      this.port.postMessage({ type: "started", key: next.key, frame: currentFrame });
    }
    return true;
  }

  finishPiece() {
    const piece = this.piece;
    this.piece = null;
    if (piece.last) {
      this.open = null;
      this.port.postMessage({ type: "completed", key: piece.key, frame: currentFrame });
    } else {
      this.open = piece.key;
    }
  }

  /**
   * Move past every piece the cursor has consumed, including empty closing pieces,
   * so a segment's completion is reported as soon as its last sample was written.
   */
  settle() {
    for (;;) {
      if (this.piece === null && !this.advance()) return false;
      if (this.position < this.piece.samples.length) return true;
      this.position -= this.piece.samples.length;
      if (this.piece.samples.length > 0) this.previous = this.piece.samples[this.piece.samples.length - 1];
      this.finishPiece();
    }
  }

  /** The source sample after `index` in the current piece: the next piece's first, if it is here. */
  following(index) {
    const samples = this.piece.samples;
    if (index + 1 < samples.length) return samples[index + 1];
    for (const waiting of this.queue) if (waiting.samples.length > 0) return waiting.samples[0];
    return samples[index]; // nothing to interpolate towards yet: hold, never jump
  }

  process(_inputs, outputs) {
    const out = outputs[0] && outputs[0][0];
    if (!out) return !this.stopped;
    for (let i = 0; i < out.length; i += 1) {
      if (!this.settle()) {
        out[i] = 0;
        if (this.open !== null) this.underrunFrames += 1;
        continue;
      }
      const samples = this.piece.samples;
      const index = Math.floor(this.position);
      const fraction = this.position - index;
      out[i] = fraction === 0 ? samples[index] : samples[index] + (this.following(index) - samples[index]) * fraction;
      this.position += this.step;
    }
    this.settle();
    return !this.stopped;
  }
}
registerProcessor("val-playback", ValPlaybackProcessor);
