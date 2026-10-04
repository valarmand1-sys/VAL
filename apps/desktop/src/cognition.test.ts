import { describe, expect, it } from "vitest";
import {
  adoptNewChatChoice,
  CANCELLED_NOTICE,
  cognitionLine,
  deepFor,
  newRequestId,
  NEW_CHAT,
  type CognitionState,
} from "./cognition";

const TYPED = "styletune";
const DEEP = "gpt-oss";
const base: CognitionState = {
  configured: true,
  typed_model: TYPED,
  deep_model: DEEP,
  resident: [],
  preparing: null,
  voice_open: false,
  voice_holds_memory: false,
  typed_ready: false,
  deep_ready: false,
};

describe("the text model's line", () => {
  it("says nothing when no typed model is configured, or when the wanted model is ready", () => {
    expect(cognitionLine(null, false)).toBeNull();
    expect(cognitionLine({ configured: false }, false)).toBeNull();
    expect(cognitionLine({ ...base, resident: [TYPED], typed_ready: true }, false)).toBeNull();
    expect(cognitionLine({ ...base, resident: [DEEP], deep_ready: true }, true)).toBeNull();
  });

  it("says the wanted model is being prepared, and that a message is kept", () => {
    const line = cognitionLine({ ...base, preparing: TYPED }, false);
    expect(line).toContain("Preparing the text model");
    expect(line).toContain("kept and answered when it is ready");
    expect(cognitionLine({ ...base, preparing: DEEP }, true)).toContain("deep-reasoning model");
  });

  it("says models are changing when the other one is being brought up", () => {
    expect(cognitionLine({ ...base, preparing: DEEP }, false)).toContain("Changing models");
  });

  it("says the model is not loaded when nothing is being prepared — never that it is ready", () => {
    expect(cognitionLine({ ...base, resident: [DEEP], deep_ready: true }, false)).toContain(
      "not loaded",
    );
  });

  it("leaves Voice to say its own state", () => {
    expect(cognitionLine({ ...base, voice_open: true }, false)).toBeNull();
    expect(cognitionLine({ ...base, voice_holds_memory: true }, false)).toBeNull();
  });
});

describe("the deep-reasoning choice", () => {
  it("is per conversation and off unless chosen", () => {
    expect(deepFor({}, "a")).toBe(false);
    expect(deepFor({ a: true }, "a")).toBe(true);
    expect(deepFor({ a: true }, "b")).toBe(false);
    expect(deepFor({ [NEW_CHAT]: true }, null)).toBe(true);
  });

  it("travels from a new chat to the conversation its first message creates", () => {
    expect(adoptNewChatChoice({ [NEW_CHAT]: true, b: false }, "c")).toEqual({ b: false, c: true });
    const untouched = { a: true };
    expect(adoptNewChatChoice(untouched, "c")).toBe(untouched);
  });
});

describe("a submission", () => {
  it("has its own name, different each time", () => {
    const one = newRequestId();
    expect(one.length).toBeGreaterThanOrEqual(8);
    expect(newRequestId()).not.toBe(one);
  });

  it("when cancelled, says the message is kept and nothing was invented", () => {
    expect(CANCELLED_NOTICE).toContain("kept");
    expect(CANCELLED_NOTICE).toContain("nothing was invented");
  });
});
