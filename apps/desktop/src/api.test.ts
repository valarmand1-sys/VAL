// The failure taxonomy says only what was established — invariant 29 applied
// to error display (Lord Armand, 31 August 2026). The banner that asserted
// "not reachable" over a policy failure cost real diagnostic time; these pin
// the replacement's two rules: no unestablished cause is ever named, and
// where script cannot distinguish two causes, both are named.

import { describe, expect, it } from "vitest";

import { api, ApiRefusal, describeFailure, initFor, NoResponseError, typedWorkWaitsForVoice } from "./api";

describe("failures are described by what was observed", () => {
  it("a missing response names both possible causes and asserts neither", () => {
    const label = describeFailure(new NoResponseError(new TypeError("Load failed")));
    expect(label).toContain("no response");
    expect(label).toContain("not running");
    expect(label).toContain("blocked by policy");
    expect(label).toContain("curl");
    expect(label).not.toContain("not reachable");
  });

  it("a refusal names the status and the service's own words", () => {
    const label = describeFailure(new ApiRefusal(422, "position is required"));
    expect(label).toContain("HTTP 422");
    expect(label).toContain("position is required");
    expect(label).toContain("answered and refused");
    expect(label).not.toContain("not reachable");
  });

  it("anything else is an unexpected failure, quoted, not diagnosed", () => {
    const label = describeFailure(new SyntaxError("Unexpected token"));
    expect(label).toContain("unexpected failure");
    expect(label).toContain("Unexpected token");
    expect(label).not.toContain("not reachable");
  });
});

describe("reads are CORS-simple requests", () => {
  it("a bodiless request declares no content type, so no preflight is forced", () => {
    expect(initFor(undefined)).toEqual({});
    expect(initFor({ method: "GET" })).toEqual({ method: "GET" });
  });

  it("a request with a body declares application/json", () => {
    const init = initFor({ method: "POST", body: "{}" });
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.body).toBe("{}");
  });
});

describe("closing a voice session", () => {
  // Owner diagnostic, 25 September 2026: it must survive the window closing, and must
  // not need a preflight to leave.
  it("is a keepalive POST with no body and no headers", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({}), { status: 200 });
    }) as typeof fetch;
    try {
      await api.closeVoiceSession("01a0d100-0000-7000-8000-000000000000");
    } finally {
      globalThis.fetch = original;
    }
    const [url, init] = calls[0]!;
    expect(url).toMatch(/\/voice\/sessions\/01a0d100-0000-7000-8000-000000000000\/close$/);
    expect(init?.method).toBe("POST");
    expect(init?.keepalive).toBe(true);
    expect(init?.body).toBeUndefined();
    expect(init?.headers).toBeUndefined();
  });
});

describe("typed work waits while Voice is on (owner order, 30 September 2026)", () => {
  it("reads the service's 409 with voice_active into the explanation he sees", () => {
    const refusal = new ApiRefusal(409, { voice_active: true, message: "Voice is on. Draft kept." });
    expect(typedWorkWaitsForVoice(refusal)).toBe("Voice is on. Draft kept.");
  });
  it("is null for every other failure, so those keep their own descriptions", () => {
    expect(typedWorkWaitsForVoice(new ApiRefusal(409, "some other conflict"))).toBeNull();
    expect(typedWorkWaitsForVoice(new ApiRefusal(422, { voice_active: true }))).toBeNull();
    expect(typedWorkWaitsForVoice(new NoResponseError(new TypeError("Load failed")))).toBeNull();
  });
});

describe("a refusal reads the same on every route (physical check, 2 October 2026)", () => {
  // He typed during Voice and was shown "the service answered and refused (HTTP 409):
  // {"detail":{"voice_active":true,…}}". The streaming send kept the service's whole
  // body, so the refusal it carries was never recognised.
  const BODY = {
    detail: {
      voice_active: true,
      message: "Voice is on. Typed messages wait until Voice ends; your words stay as a draft.",
    },
  };

  it("the streaming send's 409 is recognised as typed work waiting for Voice", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify(BODY), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      })) as typeof fetch;
    let caught: unknown = null;
    try {
      await api.turnStream({ content: "What does a producer do?", no_project: true } as never, {
        onDelta: () => undefined,
        onStage: () => undefined,
      } as never);
    } catch (failure) {
      caught = failure;
    } finally {
      globalThis.fetch = original;
    }
    expect(caught).toBeInstanceOf(ApiRefusal);
    const notice = typedWorkWaitsForVoice(caught);
    expect(notice).toBe(BODY.detail.message);
    expect(notice).not.toContain("HTTP");
    expect(notice).not.toContain("{");
  });
});

