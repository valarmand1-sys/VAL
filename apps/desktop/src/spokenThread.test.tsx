// @vitest-environment jsdom
//
// Her displayed answer progresses with her speech — owner order, 25 September 2026
// (Voice-mode repair §3, §4).
//
// He heard her begin, and her text arrived later: the desktop read her answer only
// once every segment had been synthesised. These tests hold the presentation through
// the real `VoiceController`, the real `SpeechPlayer` (a fake output device whose
// buffers end when the test says so), the real read rule and the real `Thread`, and
// they assert on the document: her answer is read the moment Core has written it,
// each segment's text appears when that segment starts playing, and a stop shows the
// rest marked as not spoken.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConversationDetail, MessageView, SpeechOfferView, VoiceSessionView } from "./api";
import { api } from "./api";
import { HeardWords, Thread } from "./App";
import { latestIssuedWins } from "./conversationReads";
import type { CapturePlatform } from "./microphone";
import type { SpeakerPlatform } from "./speaker";
import type { SpokenAnswer } from "./spokenPresentation";
import { VoiceController } from "./voiceController";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const CONVERSATION = "0f0f0f0f-d67c-7052-ba5f-000000000003";
const HIS = "0f0f0f0f-0001-7000-8000-000000000001";
const HERS = "0f0f0f0f-0002-7000-8000-000000000002";
const FIRST = "Good evening, my lord. ";
const SECOND = "I am listening, and the test is running well. ";
const THIRD = "Tell me what you would like to try next.";
const ANSWER = FIRST + SECOND + THIRD;

function message(id: string, role: "user" | "val", content: string, sequence: number): MessageView {
  return { id, role, content, sequence, created_at: "2026-09-25T23:20:32Z", state: "current" };
}

function detail(messages: MessageView[]): ConversationDetail {
  return {
    conversation: {
      id: CONVERSATION,
      project_id: null,
      title: "Good evening Val.",
      started_at: "2026-09-25T23:20:32Z",
      last_message_at: "2026-09-25T23:20:32Z",
      archived: false,
    },
    messages,
    classifications: [],
    blind_positions: [],
    deliberations: [],
    execution_events: [],
  };
}

const ANSWERED = detail([
  message(HIS, "user", "Good evening Val.", 1),
  message(HERS, "val", ANSWER, 2),
]);

function session(overrides: Partial<VoiceSessionView>): VoiceSessionView {
  return {
    session: "0f0f0f0f-efbf-7672-bbd1-000000000004",
    voice_session_id: null,
    conversation_id: CONVERSATION,
    state: "thinking",
    utterance: 1,
    provisional: "",
    hearing: false,
    pending: "Good evening Val.",
    turns: [],
    recognizer: {} as VoiceSessionView["recognizer"],
    endpoint: {},
    error: null,
    delivery: null,
    cancellations_ms: [],
    committed: { conversation_id: CONVERSATION, message_id: HIS, utterance: 1 },
    answered: { conversation_id: CONVERSATION, message_id: HERS, utterance: 1 },
    speech_end: null,
    ...overrides,
  };
}

function offer(overrides: Partial<SpeechOfferView>): SpeechOfferView {
  return { delivery_state: "started", stop: false, reason: null, segment: null, message_id: HERS, ...overrides };
}

function segment(index: number, text: string): SpeechOfferView {
  return offer({
    segment: {
      message_id: HERS,
      segment_index: index,
      text,
      audio_format: "wav",
      sample_rate: 24_000,
      duration_seconds: 1,
      audio_bytes: 4,
      audio_base64: "AAAAAA==",
    } as SpeechOfferView["segment"],
  });
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

/** An output device whose buffers finish only when the test ends them. */
const playing: Array<{ onended: (() => void) | null }> = [];
const speaker: SpeakerPlatform = {
  createContext: () =>
    ({
      decodeAudioData: async () => ({ duration: 1 }),
      createBufferSource: () => {
        const source = { onended: null as (() => void) | null, connect() {}, disconnect() {}, start() {}, stop() {} };
        playing.push(source);
        return source;
      },
      close: async () => undefined,
      destination: {},
    }) as unknown as AudioContext,
};

let container: HTMLDivElement;
let root: Root;

function mount() {
  let setShown: (value: ConversationDetail | null) => void = () => undefined;
  let setSpoken: (value: SpokenAnswer[]) => void = () => undefined;
  function Screen(): React.JSX.Element | null {
    const [shown, set] = useState<ConversationDetail | null>(null);
    const [spoken, spokenSet] = useState<SpokenAnswer[]>([]);
    setShown = set;
    setSpoken = spokenSet;
    if (shown === null) return null;
    return (
      <Thread
        detail={shown}
        projects={[]}
        spoken={spoken}
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
      onOwnerMessageCommitted: (committed) => void reads.read(() => api.conversation(committed.conversation_id)),
      onAnswerAvailable: (answered) => void reads.read(() => api.conversation(answered.conversation_id)),
      onSpoken: (answers) => setSpoken(answers),
      onTurnSettled: (view) => void reads.read(() => api.conversation(view.turns.at(-1)!.conversation_id)),
    },
    capture,
    speaker,
    now: () => performance.now(),
    scheduleInterval: () => 1,
    clearScheduled: () => undefined,
  });
  const internals = controller as unknown as { poll(): Promise<void>; collectSpeech(): Promise<void> };
  return { controller, poll: internals.poll.bind(controller), collect: internals.collectSpeech.bind(controller) };
}

/** Let the player decode and schedule what it was given. */
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await act(async () => Promise.resolve());
}

function text(): string {
  return container.textContent ?? "";
}

beforeEach(() => {
  playing.length = 0;
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
  vi.spyOn(api, "reportPlayback").mockResolvedValue(undefined as never);
  vi.spyOn(api, "deliveredVoiceTurn").mockResolvedValue(undefined as never);
  vi.spyOn(api, "reportVoiceTimings").mockResolvedValue(undefined);
  vi.spyOn(api, "voiceSession").mockResolvedValue(session({}) as never);
  vi.spyOn(api, "conversation").mockResolvedValue(ANSWERED);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("her answer is shown as she speaks it", () => {
  it("is read when Core has written it, and shown one segment at a time, at playback start", async () => {
    const { controller, poll, collect } = mount();
    await controller.start({ no_project: true });
    // The session announces her answer before any audio exists.
    await act(async () => poll());
    expect(api.conversation).toHaveBeenCalled();
    expect(text()).toContain("Good evening Val.");
    expect(text()).not.toContain("Good evening, my lord.");

    // Her first segment is collected and scheduled: its text appears, and only it.
    vi.spyOn(api, "collectSpeech").mockResolvedValue(segment(0, FIRST) as never);
    await act(async () => collect());
    await settle();
    expect(text()).toContain("Good evening, my lord.");
    expect(text()).not.toContain("I am listening");

    // The second is collected while the first still plays: not shown yet.
    vi.spyOn(api, "collectSpeech").mockResolvedValue(segment(1, SECOND) as never);
    await act(async () => collect());
    await settle();
    expect(text()).not.toContain("I am listening");
    // The first ends; the second starts; its text appears.
    await act(async () => playing[0]!.onended?.());
    await settle();
    expect(text()).toContain("I am listening");
    expect(text()).not.toContain("Tell me what");

    vi.spyOn(api, "collectSpeech").mockResolvedValue(segment(2, THIRD) as never);
    await act(async () => collect());
    vi.spyOn(api, "collectSpeech").mockResolvedValue(offer({ delivery_state: "completed" }) as never);
    await act(async () => collect());
    await act(async () => playing[1]!.onended?.());
    await settle();
    expect(text()).toContain(ANSWER.trim());
    expect(text()).not.toContain("Not spoken");
    await controller.stop();
  });

  it("an interruption shows the rest at once, marked as not spoken", async () => {
    const { controller, poll, collect } = mount();
    await controller.start({ no_project: true });
    await act(async () => poll());
    vi.spyOn(api, "collectSpeech").mockResolvedValue(segment(0, FIRST) as never);
    await act(async () => collect());
    await settle();
    vi.spyOn(api, "collectSpeech").mockResolvedValue(
      offer({ delivery_state: "interrupted", stop: true, reason: "the owner spoke" }) as never,
    );
    await act(async () => collect());
    await settle();
    expect(text()).toContain("Tell me what you would like to try next.");
    expect(text()).toContain("Not spoken — Val was interrupted.");
    await controller.stop();
  });

  it("Voice ending never strands her text", async () => {
    const { controller, poll } = mount();
    await controller.start({ no_project: true });
    await act(async () => poll());
    expect(text()).not.toContain("Good evening, my lord.");
    await act(async () => controller.stop());
    expect(text()).toContain(ANSWER.trim());
    expect(text()).toContain("Not spoken — Voice ended.");
  });
});

describe("his next words committed while she is still speaking (his session of 25 Sept)", () => {
  const LATER = "0f0f0f0f-0003-7000-8000-000000000005";
  it("does not mark the answer she is speaking as unspoken, and does not report the wrong turn", async () => {
    const { controller, poll, collect } = mount();
    const reported = vi.spyOn(api, "reportVoiceTimings").mockResolvedValue(undefined);
    await controller.start({ no_project: true });
    await act(async () => poll());
    vi.spyOn(api, "collectSpeech").mockResolvedValue(segment(0, FIRST) as never);
    await act(async () => collect());
    await settle();
    vi.spyOn(api, "collectSpeech").mockResolvedValue(segment(1, SECOND) as never);
    await act(async () => collect());
    await settle();
    // His queued utterance is committed now, while her second segment waits to play.
    vi.spyOn(api, "voiceSession").mockResolvedValue(
      session({
        utterance: 2,
        pending: "",
        committed: { conversation_id: CONVERSATION, message_id: LATER, utterance: 2 },
      }) as never,
    );
    await act(async () => poll());
    expect(text()).not.toContain("Not spoken");
    expect(text()).not.toContain("I am listening");
    // Her second segment still plays, and appears as it does.
    await act(async () => playing[0]!.onended?.());
    await settle();
    expect(text()).toContain("I am listening");
    expect(text()).not.toContain("Not spoken");
    // No owner-facing interval pairs his new words with her earlier answer.
    const paired = reported.mock.calls.filter(([, body]) => body.utterance === 2);
    expect(paired.every(([, body]) => body.speech_end_to_playback_start_ms === null)).toBe(true);
    await controller.stop();
  });
});

describe("a segment voiced before her answer was written", () => {
  it("is reported under her answer's id once it is known, never under the placeholder", async () => {
    const { controller, poll, collect } = mount();
    const played = vi.spyOn(api, "reportPlayback").mockResolvedValue(undefined as never);
    await controller.start({ no_project: true });
    // His words are committed; her answer is not yet written.
    vi.spyOn(api, "voiceSession").mockResolvedValue(session({ answered: null }) as never);
    await act(async () => poll());
    const unbound = segment(0, FIRST);
    unbound.segment!.message_id = "00000000-0000-0000-0000-000000000000";
    unbound.message_id = null;
    vi.spyOn(api, "collectSpeech").mockResolvedValue(unbound as never);
    await act(async () => collect());
    await settle();
    expect(played).not.toHaveBeenCalled();
    // Her answer is announced: the held report goes out under its id.
    vi.spyOn(api, "voiceSession").mockResolvedValue(session({}) as never);
    await act(async () => poll());
    expect(played).toHaveBeenCalledTimes(1);
    const [, body] = played.mock.calls[0]!;
    expect(body.message_id).toBe(HERS);
    expect(body.state).toBe("playback_started");
    expect(body.observed_ms_ago).toBeGreaterThanOrEqual(0);
    expect(text()).toContain("Good evening, my lord.");
    await controller.stop();
  });
});

describe("his words, before they are his message", () => {
  function renderHeard(view: VoiceSessionView, shown: ConversationDetail | null) {
    act(() => root.render(<HeardWords session={view} detail={shown} />));
  }

  it("shows his settled words, plainly provisional, until the canonical message is in the thread", () => {
    const settled = session({ committed: null, answered: null, conversation_id: null });
    renderHeard(settled, null);
    expect(text()).toContain("Good evening Val.");
    expect(text()).toContain("not yet your message");
    // Committed and read: the provisional copy is gone, so his words appear once.
    renderHeard(session({}), ANSWERED);
    expect(text()).toBe("");
  });

  it("shows what is being heard as a guess in progress", () => {
    renderHeard(session({ committed: null, pending: "", hearing: true, provisional: "Good eve" }), null);
    expect(text()).toContain("Good eve");
    expect(text()).toContain("Hearing…");
  });

  it("is not shown in another conversation", () => {
    const elsewhere = { ...ANSWERED, conversation: { ...ANSWERED.conversation, id: "somewhere-else" } };
    renderHeard(session({ committed: null }), elsewhere);
    expect(text()).toBe("");
  });
});
