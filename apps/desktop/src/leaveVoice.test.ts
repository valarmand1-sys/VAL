// Asking before ending Voice — owner acceptance repair, §5 and §19.
//
// The release itself is the ruling and is unchanged: Voice never carries its
// microphone or its session silently into another conversation. What he objected to
// was learning about it afterwards, from a notice. So the change is intercepted
// before it happens.
//
// The guard is one small function in `App.tsx`; these tests hold its two branches
// against a stand-in with exactly its shape, because what matters is the order of
// operations — ask, then release, then navigate — and that cancelling changes
// nothing at all.

import { describe, expect, it } from "vitest";

import { LEAVING_VOICE_CONFIRMATION } from "./voiceState";

/** The guard, as `App.tsx` composes it. */
function guard(options: {
  voiceIsOn: boolean;
  answer: boolean;
  onConfirm: () => Promise<void>;
  asked: string[];
}) {
  return async (): Promise<boolean> => {
    if (!options.voiceIsOn) return true;
    options.asked.push(LEAVING_VOICE_CONFIRMATION);
    if (!options.answer) return false;
    await options.onConfirm();
    return true;
  };
}

describe("a conversation change while Voice is on", () => {
  it("asks first, in words that say what will happen", () => {
    expect(LEAVING_VOICE_CONFIRMATION).toContain("end Voice");
    expect(LEAVING_VOICE_CONFIRMATION).toContain("release the microphone");
    expect(LEAVING_VOICE_CONFIRMATION).toContain("Continue?");
  });

  it("changes nothing when he cancels", async () => {
    const asked: string[] = [];
    let released = 0;
    const mayLeave = guard({
      voiceIsOn: true,
      answer: false,
      onConfirm: async () => {
        released += 1;
      },
      asked,
    });

    const permitted = await mayLeave();

    expect(permitted).toBe(false);
    expect(asked).toEqual([LEAVING_VOICE_CONFIRMATION]);
    // Not released, not muted, not navigated: exactly as it was.
    expect(released).toBe(0);
  });

  it("ends Voice through the governed path before navigating, when he confirms", async () => {
    const order: string[] = [];
    const mayLeave = guard({
      voiceIsOn: true,
      answer: true,
      onConfirm: async () => {
        order.push("voice off");
      },
      asked: [],
    });

    const permitted = await mayLeave();
    if (permitted) order.push("navigate");

    expect(permitted).toBe(true);
    // The order is the contract: the device is released before the conversation
    // changes, never after it and never alongside it.
    expect(order).toEqual(["voice off", "navigate"]);
  });

  it("asks nothing when Voice is already off", async () => {
    const asked: string[] = [];
    let released = 0;
    const mayLeave = guard({
      voiceIsOn: false,
      answer: false,
      onConfirm: async () => {
        released += 1;
      },
      asked,
    });

    expect(await mayLeave()).toBe(true);
    expect(asked).toEqual([]);
    expect(released).toBe(0);
  });
});

describe("the guard is on every navigation that changes the active conversation", () => {
  it("covers opening a conversation, New chat, entering a project and leaving one", async () => {
    // Structural: a navigation handler that forgot the guard is the defect, and it
    // would not be visible in a rendered test that happened not to click it.
    const modules = import.meta.glob("./App.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    });
    const source = String(Object.values(modules)[0]);
    // Every call that changes which conversation is open sits behind the guard.
    for (const navigation of [
      "await openConversation(conversation.id);",
      "newChat();",
      "await chooseScope({ kind: \"all\" });",
      "await chooseScope({ kind: \"project\", project });",
      "setEntry(enterProject(scope.project));",
    ]) {
      const at = source.indexOf(navigation);
      expect(at, `${navigation} is not in App.tsx`).toBeGreaterThan(-1);
      const before = source.slice(Math.max(0, at - 320), at);
      expect(before, `${navigation} is not behind mayLeaveConversation`).toContain(
        "mayLeaveConversation",
      );
    }
  });
});
