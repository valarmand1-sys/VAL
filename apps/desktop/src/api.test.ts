// The failure taxonomy says only what was established — invariant 29 applied
// to error display (Lord Armand, 31 August 2026). The banner that asserted
// "not reachable" over a policy failure cost real diagnostic time; these pin
// the replacement's two rules: no unestablished cause is ever named, and
// where script cannot distinguish two causes, both are named.

import { describe, expect, it } from "vitest";

import { ApiRefusal, describeFailure, initFor, NoResponseError } from "./api";

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
