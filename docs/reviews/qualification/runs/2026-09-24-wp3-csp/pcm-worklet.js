// A minimal same-origin AudioWorklet module, for the CSP probe only.
class ProbeProcessor extends AudioWorkletProcessor {
  process() {
    return true;
  }
}
registerProcessor("csp-probe", ProbeProcessor);
