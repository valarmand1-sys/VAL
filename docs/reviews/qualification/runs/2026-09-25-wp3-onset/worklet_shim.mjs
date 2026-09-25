// Runs the desktop's shipped `public/pcm-worklet.js` — the file itself, not a copy —
// outside a browser, so the probe exercises the real resampling and chunking.
//
// stdin: little-endian float32 mono PCM at the capture rate given in argv[2].
// stdout: the int16 chunks the worklet posted, concatenated in posting order.
// stderr: one JSON line with the counts.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  path.resolve(here, "../../../../../apps/desktop/public/pcm-worklet.js"),
  "utf8",
);
const captureRate = Number(process.argv[2]);
const quantum = 128; // the Web Audio render quantum
const posted = [];
let registered = null;
const context = {
  sampleRate: captureRate,
  registerProcessor: (_name, cls) => {
    registered = cls;
  },
  AudioWorkletProcessor: class {
    constructor() {
      this.port = { postMessage: (buffer) => posted.push(new Int16Array(buffer)) };
    }
  },
  Float32Array,
  Int16Array,
  Math,
};
vm.createContext(context);
vm.runInContext(source, context);
const processor = new registered({ processorOptions: { targetRate: 16000, chunkSamples: 320 } });

const chunks = [];
for await (const piece of process.stdin) chunks.push(piece);
const raw = Buffer.concat(chunks);
const input = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
let quanta = 0;
for (let start = 0; start < input.length; start += quantum) {
  const block = input.slice(start, Math.min(input.length, start + quantum));
  processor.process([[block]]);
  quanta += 1;
}
let total = 0;
for (const chunk of posted) {
  process.stdout.write(Buffer.from(chunk.buffer));
  total += chunk.length;
}
process.stderr.write(
  JSON.stringify({ input_samples: input.length, quanta, chunks: posted.length, output_samples: total }) + "\n",
);
