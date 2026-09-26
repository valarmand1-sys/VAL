// A speaker platform for tests that runs the REAL playback worklet.
//
// `public/pcm-playback-worklet.js` is loaded as source and its processor class
// instantiated behind a fake `AudioWorkletNode`, with a fake message port in each
// direction. Tests then pump output frames through `process` themselves, so what is
// asserted is the shipped worklet's behaviour — the joins, the events, the stop — not
// a stand-in for it.

// The shipped worklet's source, exactly as the desktop serves it.
import WORKLET_SOURCE from "../public/pcm-playback-worklet.js?raw";
import type { SpeakerPlatform } from "./speaker";

class FakePort {
  onmessage: ((event: { data: unknown }) => void) | null = null;
  other: FakePort | null = null;
  postMessage(data: unknown): void {
    this.other?.onmessage?.({ data });
  }
}

class FakeProcessorBase {
  port = new FakePort();
}

interface Processor {
  port: FakePort;
  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean;
}

/** The device side of one test: frames pumped, output collected, time advanced. */
export class PlaybackHarness {
  processor: Processor | null = null;
  frame = 0;
  requestedRate: number | null = null;
  readonly output: number[] = [];
  closed = 0;

  constructor(readonly contextRate = 24000) {}

  /** Write `frames` output samples through the real processor. */
  pump(frames: number): Float32Array {
    const out = new Float32Array(frames);
    if (this.processor !== null) this.processor.process([], [[out]]);
    this.frame += frames;
    for (let i = 0; i < frames; i += 1) this.output.push(out[i] ?? 0);
    return out;
  }

  /** Pump in blocks until `predicate` holds or `limitFrames` have passed. */
  pumpUntil(predicate: () => boolean, limitFrames = 24000 * 30, block = 128): void {
    let pumped = 0;
    while (!predicate() && pumped < limitFrames) {
      this.pump(block);
      pumped += block;
    }
  }

  platform(): SpeakerPlatform {
    const harness = this;
    let processorClass: (new (options: unknown) => Processor) | null = null;
    // The worklet's globals: its base class, the registrar, and the two live values.
    Object.defineProperty(globalThis, "sampleRate", {
      configurable: true,
      get: () => harness.contextRate,
    });
    Object.defineProperty(globalThis, "currentFrame", {
      configurable: true,
      get: () => harness.frame,
    });
    new Function("AudioWorkletProcessor", "registerProcessor", WORKLET_SOURCE)(
      FakeProcessorBase,
      (_name: string, klass: new (options: unknown) => Processor) => {
        processorClass = klass;
      },
    );
    // Installed when the player asks for its context — after a test's own microphone
    // fakes have installed theirs — and answering for both worklets: the playback
    // processor by name, and a silent stub for the capture worklet.
    const install = () => {
      (globalThis as Record<string, unknown>).AudioWorkletNode = class {
        port = new FakePort();
        constructor(_context: unknown, name: string, options: unknown) {
          if (name !== "val-playback") return;
          if (processorClass === null) throw new Error("the worklet registered no processor");
          const processor = new processorClass(options);
          processor.port.other = this.port;
          this.port.other = processor.port;
          harness.processor = processor;
        }
        connect(): void {}
        disconnect(): void {}
      };
    };
    return {
      createContext: (rate: number) => {
        install();
        harness.requestedRate = rate;
        return {
          sampleRate: harness.contextRate,
          destination: {},
          audioWorklet: { addModule: async () => undefined },
          close: async () => {
            harness.closed += 1;
          },
        } as unknown as AudioContext;
      },
      workletModuleUrl: "/pcm-playback-worklet.js",
    };
  }
}

/** A 16-bit mono WAV of `samples` at `rate` Hz, as bytes. */
export function wavBytes(samples: ArrayLike<number>, rate = 24000): ArrayBuffer {
  const data = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(data);
  const ascii = (at: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(at + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    view.setInt16(44 + i * 2, Math.round(Math.max(-1, Math.min(1, samples[i] ?? 0)) * 32767), true);
  }
  return data;
}

/** A ramp of `n` samples from `from` to `to`: distinguishable, and joinable seamlessly. */
export function ramp(n: number, from: number, to: number): number[] {
  return Array.from({ length: n }, (_, i) => from + ((to - from) * i) / Math.max(1, n - 1));
}

export function wavBase64(samples: ArrayLike<number>, rate = 24000): string {
  const bytes = new Uint8Array(wavBytes(samples, rate));
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i] ?? 0);
  return btoa(binary);
}
