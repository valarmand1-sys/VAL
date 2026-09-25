// @vitest-environment jsdom
//
// His words are on screen while she is still thinking — owner diagnostic, 25 Sept 2026.
//
// He said "Good evening, Val." and saw nothing until her answer appeared, twice. The
// previous repair's test asserted that a callback fired over a scripted session in
// which an "asked" turn existed; the real service never produced one, so the test
// passed while he saw nothing. These tests hold the **presentation**: the real
// `VoiceController` polling, the real read path with its stale-response rule, and
// the real `Thread` the conversation view mounts — and they assert on the document.
//
// "Cognition unfinished" is literal here: the session the controller polls says
// `thinking`, has no answered turn, and the answer read has not been issued, when
// the assertions about his message are made.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConversationDetail, MessageView, VoiceSessionView } from "./api";
import { api } from "./api";
import { Thread } from "./App";
import { latestIssuedWins } from "./conversationReads";
import type { CapturePlatform } from "./microphone";
import type { SpeakerPlatform } from "./speaker";
import { VoiceController } from "./voiceController";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const CONVERSATION = "01a0d68e-15e5-7479-b288-901e0c548ce4";
const HIS = "01a0d68e-15ea-7a44-b274-bb13212af7b9";
const HERS = "01a0d68e-3d75-7fbc-ae6c-c32f3d46009f";

function message(id: string, role: "user" | "val", content: string, sequence: number): MessageView {
  return { id, role, content, sequence, created_at: "2026-09-25T03:13:51Z", state: "current" };
}

function detail(messages: MessageView[]): ConversationDetail {
  return {
    conversation: {
      id: CONVERSATION,
      project_id: null,
      title: "evening Val.",
      started_at: "2026-09-25T03:13:51Z",
      last_message_at: "2026-09-25T03:13:51Z",
      archived: false,
    },
    messages,
    classifications: [],
    blind_positions: [],
    deliberations: [],
    execution_events: [],
  };
}

const ASKED = detail([message(HIS, "user", "Good evening, Val.", 1)]);
const ANSWERED = detail([
  message(HIS, "user", "Good evening, Val.", 1),
  message(HERS, "val", "Good evening, my lord.", 2),
]);

function session(overrides: Partial<VoiceSessionView>): VoiceSessionView {
  return {
    session: "01a0d100-0000-7000-8000-000000000000",
    voice_session_id: null,
    conversation_id: null,
    state: "listening",
    utterance: 1,
    provisional: "",
    hearing: false,
    pending: "",
    turns: [],
    recognizer: {} as VoiceSessionView["recognizer"],
    endpoint: {},
    error: null,
    delivery: null,
    cancellations_ms: [],
    committed: null,
    ...overrides,
  };
}

/** He has stopped speaking; the service holds his settled words. */
const SETTLED = session({ state: "thinking", pending: "Good evening, Val." });
/** His words are canonical; she is thinking; nothing is answered. */
const THINKING = session({
  state: "thinking",
  pending: "Good evening, Val.",
  conversation_id: CONVERSATION,
  committed: { conversation_id: CONVERSATION, message_id: HIS, utterance: 1 },
});
/** She has answered. */
const DONE = session({
  state: "listening",
  conversation_id: CONVERSATION,
  committed: { conversation_id: CONVERSATION, message_id: HIS, utterance: 1 },
  turns: [
    {
      message_id: HIS,
      conversation_id: CONVERSATION,
      text: "Good evening, Val.",
      answer: { kind: "answered" },
    } as unknown as VoiceSessionView["turns"][number],
  ],
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const capture: CapturePlatform = {
  getUserMedia: async () => {
    const track = { readyState: "live", stop() {} };
    return { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream;
  },
  createContext: () =>
    ({
      audioWorklet: { addModule: async () => undefined },
      createMediaStreamSource: () => ({ connect() {}, disconnect() {} }),
      close: async () => undefined,
    }) as unknown as AudioContext,
  workletModuleUrl: "/pcm-worklet.js",
};

const speaker: SpeakerPlatform = {
  createContext: () =>
    ({
      decodeAudioData: async () => ({ duration: 0.1 }),
      createBufferSource: () => ({ connect() {}, disconnect() {}, start() {}, stop() {} }),
      close: async () => undefined,
      destination: {},
    }) as unknown as AudioContext,
};

let container: HTMLDivElement;
let root: Root;

/** The conversation view as the app composes it: detail state behind the read rule. */
function mount() {
  let setShown: (value: ConversationDetail | null) => void = () => undefined;
  function Screen(): React.JSX.Element | null {
    const [shown, set] = useState<ConversationDetail | null>(null);
    setShown = set;
    if (shown === null) return null;
    return (
      <Thread
        detail={shown}
        projects={[]}
        onRecorded={() => undefined}
        onConversationChanged={async () => undefined}
        onRefused={() => undefined}
      />
    );
  }
  act(() => root.render(<Screen />));
  const reads = latestIssuedWins<ConversationDetail>((value) => setShown(value));
  const controller = new VoiceController({
    hooks: {
      onStatus: () => undefined,
      onSession: () => undefined,
      onTimings: () => undefined,
      onOwnerMessageCommitted: (committed) =>
        void reads.read(() => api.conversation(committed.conversation_id)),
      onTurnSettled: (view) =>
        void reads.read(() => api.conversation(view.turns.at(-1)!.conversation_id)),
    },
    capture,
    speaker,
    now: () => performance.now(),
    scheduleInterval: () => 1,
    clearScheduled: () => undefined,
  });
  const poll = (controller as unknown as { poll(): Promise<void> }).poll.bind(controller);
  return { controller, poll };
}

function text(): string {
  return container.textContent ?? "";
}

function count(needle: string): number {
  return text().split(needle).length - 1;
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  (globalThis as Record<string, unknown>).AudioWorkletNode = class {
    port = { onmessage: null };
    connect(): void {}
    disconnect(): void {}
  };
  vi.spyOn(api, "openVoiceSession").mockResolvedValue(session({}) as never);
  vi.spyOn(api, "closeVoiceSession").mockResolvedValue(session({}) as never);
  vi.spyOn(api, "sendVoiceAudio").mockResolvedValue(undefined);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("his spoken words, while she is thinking", () => {
  it("are rendered in the thread before any answer exists", async () => {
    const { controller, poll } = mount();
    await controller.start({ no_project: true });
    const reads: Array<ReturnType<typeof deferred<ConversationDetail>>> = [];
    const conversation = vi.spyOn(api, "conversation").mockImplementation(() => {
      const next = deferred<ConversationDetail>();
      reads.push(next);
      return next.promise;
    });

    // He has stopped speaking. Nothing is canonical yet, so nothing is read.
    vi.spyOn(api, "voiceSession").mockResolvedValue(SETTLED as never);
    await act(async () => poll());
    expect(conversation).not.toHaveBeenCalled();

    // His words are committed. She is thinking: the session says so, and has no
    // answered turn. The read is issued now…
    vi.spyOn(api, "voiceSession").mockResolvedValue(THINKING as never);
    await act(async () => poll());
    expect(conversation).toHaveBeenCalledTimes(1);
    expect(conversation).toHaveBeenLastCalledWith(CONVERSATION);

    // …its response arrives, and the thread shows him his own words.
    await act(async () => reads[0]!.resolve(ASKED));
    expect(text()).toContain("Lord Armand");
    expect(text()).toContain("Good evening, Val.");
    expect(text()).not.toContain("Good evening, my lord.");
    // Still thinking: polling again does not re-read, and nothing has been answered.
    await act(async () => poll());
    expect(conversation).toHaveBeenCalledTimes(1);
    await controller.stop();
  });

  it("stay on screen when an earlier read returns after the answer's", async () => {
    const { controller, poll } = mount();
    await controller.start({ no_project: true });
    const reads: Array<ReturnType<typeof deferred<ConversationDetail>>> = [];
    vi.spyOn(api, "conversation").mockImplementation(() => {
      const next = deferred<ConversationDetail>();
      reads.push(next);
      return next.promise;
    });

    vi.spyOn(api, "voiceSession").mockResolvedValue(THINKING as never);
    await act(async () => poll());
    vi.spyOn(api, "voiceSession").mockResolvedValue(DONE as never);
    await act(async () => poll());
    expect(reads).toHaveLength(2);

    // The answer's read returns first…
    await act(async () => reads[1]!.resolve(ANSWERED));
    expect(count("Good evening, Val.")).toBe(1);
    expect(count("Good evening, my lord.")).toBe(1);
    // …then the older one. It must not take her answer away, and must not add a
    // second copy of his words.
    await act(async () => reads[0]!.resolve(ASKED));
    expect(count("Good evening, Val.")).toBe(1);
    expect(count("Good evening, my lord.")).toBe(1);
    await controller.stop();
  });

  it("are not duplicated when the answer's read replaces the first", async () => {
    const { controller, poll } = mount();
    await controller.start({ no_project: true });
    const reads: Array<ReturnType<typeof deferred<ConversationDetail>>> = [];
    vi.spyOn(api, "conversation").mockImplementation(() => {
      const next = deferred<ConversationDetail>();
      reads.push(next);
      return next.promise;
    });

    vi.spyOn(api, "voiceSession").mockResolvedValue(THINKING as never);
    await act(async () => poll());
    await act(async () => reads[0]!.resolve(ASKED));
    expect(count("Good evening, Val.")).toBe(1);

    vi.spyOn(api, "voiceSession").mockResolvedValue(DONE as never);
    await act(async () => poll());
    await act(async () => reads[1]!.resolve(ANSWERED));
    expect(count("Good evening, Val.")).toBe(1);
    expect(count("Good evening, my lord.")).toBe(1);
    await controller.stop();
  });
});
