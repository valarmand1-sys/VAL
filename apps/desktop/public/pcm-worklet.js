// Val's microphone processor — owner execution order, 24 September 2026, §10.
//
// **A file served by the application, deliberately.** It was first loaded from a
// `blob:` URL, and the desktop's Content Security Policy — `default-src 'self'`
// with no `script-src` — refused it: "Loading the script 'blob:…' violates the
// following Content Security Policy directive: \"default-src 'self'\"". That
// refusal was correct, and the fix is to stop asking for the exception rather than
// to grant one: served from the app's own origin, this module satisfies
// `default-src 'self'` and **no policy change was needed**.
//
// It runs on the audio thread, converts to the recognizer's contract — 16 kHz,
// mono, signed int16 little-endian — and posts bounded chunks. It keeps one small
// buffer and no history, and it transfers each chunk rather than copying it onward,
// so the audio thread holds no second copy of what it has just sent.
//
// Resampling is a plain decimating average, which is enough for speech at these
// rates: the alternative is a filter design exercise for audio that whisper.cpp
// then resamples internally anyway.
class ValPcmProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const settings = (options && options.processorOptions) || {};
    // Both are supplied by `processorOptions` on every construction; these are the
    // fallbacks, and `microphone.test.ts` asserts they equal TARGET_SAMPLE_RATE and
    // CHUNK_SAMPLES, so the file and the code cannot drift apart.
    this.targetRate = settings.targetRate || 16000;
    this.chunkSamples = settings.chunkSamples || 320;
    this.ratio = sampleRate / this.targetRate;
    this.pending = new Float32Array(this.chunkSamples);
    this.held = 0;
    this.position = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;
    // Down-mix to mono by averaging whatever channels arrived.
    const frames = channel.length;
    for (let index = 0; index < frames; index += 1) {
      let sum = 0;
      for (let c = 0; c < input.length; c += 1) sum += input[c][index] || 0;
      const mono = sum / input.length;
      this.position += 1;
      if (this.position < this.ratio) continue;
      this.position -= this.ratio;
      this.pending[this.held] = mono;
      this.held += 1;
      if (this.held === this.chunkSamples) {
        const out = new Int16Array(this.chunkSamples);
        for (let s = 0; s < this.chunkSamples; s += 1) {
          const clamped = Math.max(-1, Math.min(1, this.pending[s]));
          out[s] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
        }
        this.port.postMessage(out.buffer, [out.buffer]);
        this.held = 0;
      }
    }
    return true;
  }
}
registerProcessor('val-pcm', ValPcmProcessor);
