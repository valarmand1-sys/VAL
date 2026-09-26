// No desktop test reaches a real service — found 25 September 2026.
//
// Tests that left one API call unmocked sent it, through Node's real `fetch`, to
// whatever was listening on the service's loopback port: during development that is
// Val's production service. Those requests were refused (unknown session ids), but a
// test must not be able to reach the owner's house at all. Every test starts with a
// `fetch` that refuses; a test that needs one installs its own, as several already do.
import { beforeEach } from "vitest";

beforeEach(() => {
  globalThis.fetch = (async (input: unknown) => {
    throw new Error(`a test tried to reach a real service: ${String(input)}`);
  }) as typeof fetch;
});
