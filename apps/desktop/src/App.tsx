// The text interface — WP-0.10.
//
// Everything rendered here is a projection of what the service returned, and
// the service's contracts are projections of authoritative rows. The two
// rulings of 19 August 2026 for this package are enforced in
// `presentation.ts` (tested directly): a contaminated position is named as
// such and never presented as independently formed, and no outcome word is
// shown until a deliberations row supports it — pending means pending.
//
// Marking an exchange consequential and recording an execution event both
// live on the messages they are about, in the flow of working, because the
// two accumulation criteria die if either requires leaving the conversation.

import { Fragment, useCallback, useEffect, useRef, useState } from "react";

import type {
  AttachmentClassification,
  AttachmentInput,
  Confidence,
  ConversationDetail,
  ConversationView,
  CostView,
  HumanClassification,
  LabelledExchangeView,
  MessageView,
  Outcome,
  ProjectView,
  QueuedExchangeView,
  ReviewConclusion,
  ReviewProgressView,
  TurnClarification,
  VoiceSessionView,
} from "./api";
import { Attachments } from "./attachments";
import {
  NO_TIMINGS,
  VoiceController,
  type VoiceTimings,
} from "./voiceController";
import {
  MUTE_SHORTCUT_LABEL,
  registerMuteShortcut,
  tauriBinding,
  unregisterMuteShortcut,
  type ShortcutBinding,
} from "./voiceShortcut";
import {
  LEAVING_VOICE_CONFIRMATION,
  VOICE_OFF,
  describeVoice,
  micControlLabel,
  type VoiceStatus,
} from "./voiceState";
import type { Inline } from "./markdown";
import { parseMarkdown } from "./markdown";
import { api, ApiRefusal, describeFailure, HARD_EXCLUSIONS, NONE_FAILS_INCLUSION_TEST, StreamRefused } from "./api";
import {
  AGREEMENT_WORDS,
  CONCLUSION_WORDS,
  describeDeliberation,
  describeUnanswered,
  determinationLabel,
  outcomeLabel,
  progressLine,
  resolutionOf,
} from "./presentation";
import {
  answerStateLine,
  canEdit,
  canRemove,
  EDIT_EXPLANATION,
  isLive,
  moveConfirmation,
  REMOVE_CONVERSATION_CONFIRMATION,
  REMOVE_MESSAGE_CONFIRMATION,
  REMOVED_CONVERSATION_NOTICE,
  transitionLine,
  userStateLine,
} from "./messageState";
import { enterProject, initialEntry, newChatEntry, newConversationLine, turnScopeFields } from "./scope";
import { newTurnClock, PROGRESS_NOTE, STAGE_WORDS, timingLines } from "./timing";
import type { TurnClock, TurnStage, TurnTimingReport } from "./timing";
import type { Entry } from "./scope";

// The sidebar's listing filter: everything, or one project. Ruled 11 September
// 2026: "No project" is not a scope a person chooses — unassigned conversations
// are simply part of everything.
type Scope = { kind: "project"; project: ProjectView } | { kind: "all" };

// One turn in flight, shown as Val's words arrive through the service — the
// responsiveness phase, 11 September 2026. Presentation of generation in
// progress: the settled, persisted message replaces it when the turn ends.
// `stage` is the house's backend-confirmed progress (13 September 2026), shown
// only until Val's first words arrive.
interface Streaming {
  userContent: string;
  text: string;
  stage: TurnStage | null;
}

function windowVisible(): boolean {
  return typeof document === "undefined" || document.visibilityState === "visible";
}

export function App(): React.JSX.Element {
  const [projects, setProjects] = useState<ProjectView[]>([]);
  const [scope, setScope] = useState<Scope>({ kind: "all" });
  // Ruled 10 and 11 September 2026: a new conversation is unassigned unless a
  // project was entered intentionally. Opening Val starts unassigned; New chat
  // starts unassigned and leaves any entered project; entering a project (the
  // sidebar) starts a conversation there. `conversations.project_id` is
  // immutable once held (migration 0008), so a continued conversation keeps
  // its own record's attribution regardless of what is entered here.
  const [entry, setEntry] = useState<Entry>(initialEntry());
  const [streaming, setStreaming] = useState<Streaming | null>(null);
  const [lastTiming, setLastTiming] = useState<TurnTimingReport | null>(null);
  // The in-flight turn's moments, all from Send (13 September 2026). A ref, not
  // state: recording a moment must not itself cause a render.
  const turnClock = useRef<{ startedAt: number; clock: TurnClock } | null>(null);
  const [conversations, setConversations] = useState<ConversationView[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [costs, setCosts] = useState<CostView | null>(null);
  const [lastDisagreement, setLastDisagreement] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [bootProblems, setBootProblems] = useState<string[]>([]);
  const [clarification, setClarification] = useState<TurnClarification | null>(null);
  const [pendingContent, setPendingContent] = useState<string>("");
  const [composer, setComposer] = useState("");
  // Ephemeral until sent: selecting a file writes nothing anywhere.
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  // Live voice — owner execution order, 24 September 2026. **Voice is off here on
  // every mount**, which is the whole of §1.3: launch, restart, relaunch after a
  // crash and a machine wake all arrive at this line. Nothing persists a "Voice was
  // on" preference, so there is nothing for a restore to read.
  const [voice, setVoice] = useState<VoiceStatus>(VOICE_OFF);
  const [voiceSession, setVoiceSession] = useState<VoiceSessionView | null>(null);
  const [voiceTimings, setVoiceTimings] = useState<VoiceTimings>(NO_TIMINGS);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const voiceController = useRef<VoiceController | null>(null);
  const shortcutBinding = useRef<ShortcutBinding | null>(null);
  // Whether archived rows are listed. Display scoping only — the flag carries
  // no evidentiary meaning (§2.1 amendment, 31 August 2026), and everything
  // outside the two listings is archive-blind.
  const [showArchived, setShowArchived] = useState(false);
  // Ruled 7 September 2026: the classification review queue lives beside the
  // conversation thread, never over it.
  const [view, setView] = useState<"conversation" | "review">("conversation");

  const refreshConversations = useCallback(
    async (at: Scope) => {
      // The same toggle recovers archived and removed conversations (12 September 2026).
      const archived = showArchived ? { archived: true, removed: true } : {};
      if (at.kind === "project") {
        setConversations(await api.conversations({ project_id: at.project.id, ...archived }));
      } else {
        setConversations(await api.conversations(archived));
      }
    },
    [showArchived],
  );

  const refreshSignals = useCallback(async () => {
    setCosts(await api.costs());
    const signal = await api.disagreement();
    setLastDisagreement(signal.last_disagreement_at);
  }, []);

  // Bootstrap: five independent reads, each reported individually. The old
  // version wrapped all five in one catch whose only output asserted the
  // service was "not reachable" — a cause it had not established, and on
  // 31 August 2026 a false one (the failures were CORS policy against a
  // healthy service). Now each step names itself and its actual failure, and
  // no wording claims more than what was observed (invariant 29 applied to
  // error display).
  useEffect(() => {
    void (async () => {
      const problems: string[] = [];
      const step = async (name: string, run: () => Promise<void>) => {
        try {
          await run();
        } catch (failure) {
          problems.push(`${name}: ${describeFailure(failure)}`);
        }
      };
      await step("health", async () => {
        setWarnings((await api.health()).warnings);
      });
      await step("projects", async () => {
        setProjects(await api.projects(showArchived ? { archived: true } : {}));
      });
      await step("conversations", async () => {
        await refreshConversations({ kind: "all" });
      });
      await step("costs", async () => {
        setCosts(await api.costs());
      });
      await step("disagreement signal", async () => {
        setLastDisagreement((await api.disagreement()).last_disagreement_at);
      });
      setBootProblems(problems);
    })();
  }, [refreshConversations, showArchived]);

  const openConversation = useCallback(async (id: string) => {
    setDetail(await api.conversation(id));
    setClarification(null);
  }, []);

  // Entering a project, or leaving to everything. Entering is the one intentional
  // act that makes the next new conversation project-scoped.
  const chooseScope = useCallback(
    async (next: Scope) => {
      setScope(next);
      setEntry(next.kind === "project" ? enterProject(next.project) : newChatEntry());
      setDetail(null);
      setClarification(null);
      await refreshConversations(next);
    },
    [refreshConversations],
  );

  const newChat = useCallback(() => {
    setView("conversation");
    setDetail(null);
    setClarification(null);
    setScope({ kind: "all" });
    setEntry(newChatEntry());
    void refreshConversations({ kind: "all" });
  }, [refreshConversations]);

  // The first render and the confirmed first paint of Val's words, with the
  // window's visibility at each (13 September 2026). The effect runs after the
  // render committed the text; the second animation frame runs after the frame
  // that painted it. WebKit suspends animation frames for a window that is not
  // visible, so a hidden window delays the paint figure — which is why
  // visibility is recorded beside it rather than assumed.
  useEffect(() => {
    const current = turnClock.current;
    if (streaming === null || streaming.text === "" || current === null) return;
    const { clock, startedAt } = current;
    if (clock.firstRenderMs !== null) return;
    clock.firstRenderMs = Math.round(performance.now() - startedAt);
    clock.firstRenderVisible = windowVisible();
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => {
        if (clock.firstPaintMs === null) {
          clock.firstPaintMs = Math.round(performance.now() - startedAt);
          clock.firstPaintVisible = windowVisible();
        }
      });
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
    };
  }, [streaming]);

  // Voice — owner execution order, 24 September 2026, §5, §6, §7, §8.
  //
  // Every one of these is called from an owner gesture handler and from nowhere
  // else. There is no effect that starts Voice, no timer, no resume, and no retry
  // that reacquires a device: the controller refuses anything but an owner gesture,
  // and these are the gestures.
  const voiceOn = useCallback(async () => {
    if (voiceController.current !== null) return;
    setVoiceNotice(null);
    const binding = shortcutBinding.current ?? (await tauriBinding());
    shortcutBinding.current = binding;
    const controller = new VoiceController({
      hooks: {
        onStatus: (status) => {
          setVoice(status);
          if (status.failure !== null) setVoiceNotice(status.failure);
        },
        onSession: (view) => setVoiceSession(view),
        onTimings: (measured) => setVoiceTimings(measured),
        onTurnSettled: (view) => {
          const settled = view.turns.at(-1);
          if (settled === undefined) return;
          // The canonical turn is in the store; show the conversation it belongs to.
          void openConversation(settled.conversation_id).catch(() => undefined);
        },
      },
      registerShortcut: async (toggle) => {
        const outcome = await registerMuteShortcut(binding, toggle);
        if (outcome.detail !== null) setVoiceNotice(outcome.detail);
        return outcome.registered;
      },
      unregisterShortcut: () => unregisterMuteShortcut(binding),
    });
    voiceController.current = controller;
    // The same scope rule a typed turn uses, from the same function: a continued
    // conversation sends only its id, a new one in an entered project sends the
    // project, and an unassigned one says so explicitly. Voice is not a second
    // scoping model (§1.6).
    await controller.start(turnScopeFields(entry, detail?.conversation ?? null));
  }, [detail, entry, openConversation]);

  const voiceOff = useCallback(async () => {
    const controller = voiceController.current;
    if (controller === null) return;
    await controller.stop();
    voiceController.current = null;
    setVoiceSession(null);
    setVoice(VOICE_OFF);
  }, []);

  const toggleMute = useCallback(async () => {
    await voiceController.current?.toggleMute();
  }, []);

  /**
   * Ask before a conversation change ends Voice — owner acceptance, §5.
   *
   * The release is the ruling and is unchanged: Voice never carries its microphone
   * or its session silently into another conversation. What changes is that he is
   * asked **first** rather than told afterwards. Cancelling leaves the conversation,
   * the Voice session and the microphone exactly as they were; confirming ends Voice
   * through the ordinary governed path — device released, playback stopped, shortcut
   * unbound — and only then does the navigation proceed.
   */
  const mayLeaveConversation = useCallback(async (): Promise<boolean> => {
    if (voiceController.current === null || voice.session === "off") return true;
    if (!window.confirm(LEAVING_VOICE_CONFIRMATION)) return false;
    await voiceOff();
    return true;
  }, [voice.session, voiceOff]);

  // §16. A conversation change, a window closing, and the machine suspending all
  // release the device and turn Voice off. None of them mutes-and-hopes, and none
  // of them can reacquire anything afterwards.
  useEffect(() => {
    const release = () => {
      const controller = voiceController.current;
      if (controller === null) return;
      void controller.releaseForLifecycle("app_or_machine_suspending").then(() => {
        voiceController.current = null;
        setVoice(VOICE_OFF);
        setVoiceSession(null);
      });
    };
    // A hidden or unfocused window is **not** a reason to mute (§16): he may be
    // listening while working in another application, which is exactly what the
    // global shortcut is for. So visibility is deliberately not listened to here.
    // Only the window actually going away releases.
    window.addEventListener("pagehide", release);
    window.addEventListener("beforeunload", release);
    return () => {
      window.removeEventListener("pagehide", release);
      window.removeEventListener("beforeunload", release);
    };
  }, []);

  // §16. **A conversation change turns Voice off**, releases the microphone, stops
  // playback and leaves the shortcut unbound until he starts a session again. Keyed
  // on the conversation the window is showing: opening another one, or starting a
  // new one, is a different conversation from the one he turned Voice on for, and a
  // live microphone must not follow him into it silently.
  const voiceConversation = useRef<string | null>(null);
  useEffect(() => {
    const showing = detail?.conversation.id ?? null;
    const controller = voiceController.current;
    if (controller === null) {
      voiceConversation.current = showing;
      return;
    }
    if (voiceConversation.current === null) {
      // The session was started before this conversation existed — a brand-new
      // chat, whose conversation the first spoken turn creates. Adopt it rather
      // than treating its arrival as a switch.
      voiceConversation.current = showing;
      return;
    }
    if (showing === voiceConversation.current) return;
    voiceConversation.current = showing;
    // The safety net, not the ordinary path. Every navigation that changes the
    // active conversation now asks him first (`mayLeaveConversation`) and ends Voice
    // through the governed path before moving. This catches a change that arrived by
    // some other route — and it still fails closed, because a live microphone must
    // not follow him into another conversation whatever brought him there.
    void controller.releaseForLifecycle("conversation_changed").then(() => {
      voiceController.current = null;
      setVoice(VOICE_OFF);
      setVoiceSession(null);
      setVoiceNotice(
        "Voice was turned off and the microphone released, because the conversation changed.",
      );
    });
  }, [detail?.conversation.id]);

  const send = useCallback(
    async (content: string, projectOverride?: string, attached: PendingAttachment[] = []) => {
      if (content.trim() === "" || busy) return;
      setBusy(true);
      setNotice(null);
      setClarification(null);
      const startedAt = performance.now();
      const clock = newTurnClock();
      turnClock.current = { startedAt, clock };
      const since = () => Math.round(performance.now() - startedAt);
      const onVisibility = () => clock.visibilityChanges.push({ atMs: since(), visible: windowVisible() });
      document.addEventListener("visibilitychange", onVisibility);
      setStreaming({ userContent: content, text: "", stage: null });
      try {
        const scopeFields =
          projectOverride !== undefined
            ? { project: projectOverride }
            : turnScopeFields(entry, detail?.conversation ?? null);
        const attachments =
          attached.length === 0 ? undefined : await Promise.all(attached.map(asAttachmentInput));
        const result = await api.turnStream(
          { content, ...scopeFields, progress: true, ...(attachments ? { attachments } : {}) },
          {
            onDelta: (text) => {
              if (clock.firstDeltaMs === null) {
                clock.firstDeltaMs = since();
                clock.firstDeltaVisible = windowVisible();
              }
              setStreaming((current) =>
                current === null ? current : { ...current, text: current.text + text },
              );
            },
            onStage: (stage) => {
              if (stage === "preparing_response" && clock.responseStartedMs === null) {
                clock.responseStartedMs = since();
              }
              setStreaming((current) => (current === null ? current : { ...current, stage }));
            },
          },
        );
        const completeMs = since();
        const outcome = result.settled;
        if (outcome.kind === "clarification") {
          setClarification(outcome);
          setPendingContent(content);
          return;
        }
        setComposer("");
        if (outcome.kind === "unanswered") {
          setNotice(describeUnanswered(outcome));
        }
        if (outcome.kind === "truncated") {
          setNotice(
            "The reply was cut off and is shown as evidence only — it is not her message. Ask again for a full answer.",
          );
        }
        const report: TurnTimingReport = {
          clock: { ...clock, visibilityChanges: [...clock.visibilityChanges] },
          completeMs,
          responseCallFirstTokenMs: outcome.timing.gateway_first_output_ms,
          serviceResponseStartedMs: outcome.timing.api_response_started_ms ?? null,
        };
        setLastTiming(report);
        // Evidence for the undiagnosed delta-to-paint question: the whole record,
        // in the developer console. Not persisted anywhere.
        console.info("val.turn.timing", JSON.stringify({ ...report, service: outcome.timing }));
        await openConversation(outcome.conversation.id);
        await refreshConversations(scope);
        await refreshSignals();
      } catch (failure) {
        setNotice(failure instanceof StreamRefused ? failure.detail : describeFailure(failure));
      } finally {
        document.removeEventListener("visibilitychange", onVisibility);
        turnClock.current = null;
        setStreaming(null);
        setBusy(false);
      }
    },
    [busy, detail, entry, scope, openConversation, refreshConversations, refreshSignals],
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Val</h1>
        <nav>
          <h2>Projects</h2>
          <ul>
            <li>
              <button
                className={scope.kind === "all" ? "selected" : ""}
                onClick={() => {
                  void (async () => {
                    if (!(await mayLeaveConversation())) return;
                    await chooseScope({ kind: "all" });
                  })();
                }}
              >
                Everything
              </button>
            </li>
            {projects.map((project) => (
              <li key={project.id}>
                <button
                  className={
                    scope.kind === "project" && scope.project.id === project.id ? "selected" : ""
                  }
                  onClick={() => {
                    void (async () => {
                      if (!(await mayLeaveConversation())) return;
                      await chooseScope({ kind: "project", project });
                    })();
                  }}
                >
                  {project.name}
                  {project.archived && <span className="archived-tag"> (archived)</span>}
                </button>
              </li>
            ))}
          </ul>
          <NewProjectControl
            onCreated={async (project) => {
              setProjects(await api.projects(showArchived ? { archived: true } : {}));
              await chooseScope({ kind: "project", project });
            }}
            onRefused={(message) => setNotice(message)}
          />
          <h2>Conversations</h2>
          <ul>
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  className={detail?.conversation.id === conversation.id ? "selected" : ""}
                  onClick={() => {
                    void (async () => {
                      if (!(await mayLeaveConversation())) return;
                      await openConversation(conversation.id);
                    })();
                  }}
                >
                  {conversation.title}
                  {conversation.archived && <span className="archived-tag"> (archived)</span>}
                  {conversation.removed === true && <span className="archived-tag"> (removed)</span>}
                </button>
              </li>
            ))}
          </ul>
          <button
            className="new-conversation"
            onClick={() => {
              void (async () => {
                if (!(await mayLeaveConversation())) return;
                newChat();
              })();
            }}
          >
            New chat
          </button>
          {scope.kind === "project" && (
            <button
              className="new-conversation"
              onClick={() => {
                void (async () => {
                  if (!(await mayLeaveConversation())) return;
                  setView("conversation");
                  setDetail(null);
                  setClarification(null);
                  setEntry(enterProject(scope.project));
                })();
              }}
            >
              New conversation in {scope.project.name}
            </button>
          )}
          <button
            className={view === "review" ? "new-conversation selected" : "new-conversation"}
            onClick={() => setView(view === "review" ? "conversation" : "review")}
          >
            {view === "review" ? "Back to conversations" : "Review classifications"}
          </button>
          <label className="archived-toggle">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
            />
            Show archived and removed
          </label>
        </nav>
      </aside>

      <main className="thread">
        {bootProblems.length > 0 && (
          <div className="notice">
            {bootProblems.map((problem) => (
              <p key={problem}>{problem}</p>
            ))}
          </div>
        )}
        {notice !== null && <div className="notice">{notice}</div>}
        {warnings.length > 0 && (
          <div className="warnings">
            {warnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        )}

        {view === "review" ? (
          <ReviewPanel onRefused={(message) => setNotice(message)} />
        ) : streaming !== null ? (
          <StreamingThread detail={detail} streaming={streaming} />
        ) : detail === null ? (
          <div className="empty">
            <p>{newConversationLine(entry)}</p>
          </div>
        ) : (
          <Thread
            detail={detail}
            projects={projects}
            onRecorded={() => void openConversation(detail.conversation.id)}
            onConversationChanged={async () => {
              await openConversation(detail.conversation.id);
              await refreshConversations(scope);
            }}
            onRefused={(message) => setNotice(message)}
          />
        )}
        {lastTiming !== null && streaming === null && <TimingPanel report={lastTiming} />}

        {clarification !== null && (
          <div className="clarification">
            <p>{clarification.question}</p>
            {clarification.candidates.map((candidate) => (
              <button key={candidate.project_id} onClick={() => void send(pendingContent, candidate.name)}>
                {candidate.name} ({candidate.slug})
              </button>
            ))}
          </div>
        )}

        {detail?.conversation.removed === true && streaming === null && (
          <div className="notice">{REMOVED_CONVERSATION_NOTICE}</div>
        )}
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            const attached = pending;
            for (const item of attached) URL.revokeObjectURL(item.previewUrl);
            setPending([]);
            void send(composer, undefined, attached);
          }}
        >
          <textarea
            value={composer}
            onChange={(event) => setComposer(event.target.value)}
            placeholder="Say something to Val…"
            rows={3}
          />
          {pending.length > 0 && (
            <div className="pending-attachments">
              {pending.map((item) => (
                <figure key={item.key} className="pending-attachment">
                  {/* The medium as what it is, so the owner can check he
                      attached the right one before it becomes evidence. */}
                  {item.file.type.startsWith("video/") ? (
                    <video src={item.previewUrl} controls preload="metadata" />
                  ) : item.file.type.startsWith("audio/") ? (
                    <audio src={item.previewUrl} controls preload="metadata" />
                  ) : (
                    <img src={item.previewUrl} alt={item.file.name} />
                  )}
                  <figcaption>
                    <span className="name">{item.file.name}</span>
                    {/* Per act, defaulting to Protected, resolving upward. This
                        statement governs where the image may be sent, so it is
                        set here, beside the file, rather than assumed later. */}
                    <label>
                      <span className="visually-hidden">Classification</span>
                      <select
                        value={item.classification}
                        onChange={(event) =>
                          setPending((current) =>
                            current.map((existing) =>
                              existing.key === item.key
                                ? {
                                    ...existing,
                                    classification: event.target
                                      .value as AttachmentClassification,
                                  }
                                : existing,
                            ),
                          )
                        }
                      >
                        <option value="protected">Protected</option>
                        <option value="internal">Internal</option>
                        <option value="public">Public</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        URL.revokeObjectURL(item.previewUrl);
                        setPending((current) =>
                          current.filter((existing) => existing.key !== item.key),
                        );
                      }}
                    >
                      Remove
                    </button>
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
          <div className="composer-actions">
            <label className="attach">
              Attach media
              <input
                type="file"
                /* Owner execution order, 22 September 2026: video and audio join
                   the owner's path. One video container and one audio container,
                   because a format the house cannot check is a format it should
                   not admit — and admission reads the bytes, so this list is a
                   convenience for the picker and never the authority. */
                accept={
                  "image/png,image/jpeg,image/webp,image/gif," +
                  "video/mp4,audio/wav,audio/x-wav,audio/wave"
                }
                multiple
                onChange={(event) => {
                  const chosen = Array.from(event.target.files ?? []);
                  setPending((current) => [
                    ...current,
                    ...chosen.map((file) => ({
                      key: `${file.name}:${file.size}:${file.lastModified}:${Math.random()}`,
                      file,
                      previewUrl: URL.createObjectURL(file),
                      classification: "protected" as AttachmentClassification,
                    })),
                  ]);
                  event.target.value = "";
                }}
              />
            </label>
            {/* Voice — owner execution order, 24 September 2026, §5, §9, §17.
                Beside Attach media and Send, in the composer he already uses: Voice
                is a way of saying a turn, not a separate screen or a second
                conversation. The label reports **actual** state, never requested
                state, and never by colour alone. */}
            <div className="voice-controls" role="group" aria-label="Voice">
              <button
                type="button"
                className={voice.session === "off" ? "voice-off" : "voice-on"}
                aria-pressed={voice.session !== "off"}
                onClick={() => {
                  // The one door to a microphone in this application: his click.
                  if (voice.session === "off") void voiceOn();
                  else void voiceOff();
                }}
                disabled={voice.session === "starting" || voice.session === "stopping"}
              >
                {voice.session === "off" ? "Voice on" : "Voice off"}
              </button>
              {(voice.session === "active_mic_live" || voice.session === "active_muted") && (
                <button
                  type="button"
                  className={voice.mic === "live" ? "mic-live" : "mic-muted"}
                  aria-label={micControlLabel(voice)}
                  aria-pressed={voice.mic !== "live"}
                  onClick={() => void toggleMute()}
                  disabled={voice.mic === "acquiring"}
                >
                  {voice.mic === "acquiring"
                    ? "Unmuting…"
                    : voice.mic === "live"
                      ? "Mute"
                      : "Unmute"}
                </button>
              )}
              <span className="voice-state" aria-live="polite">
                {describeVoice(voice)}
                {voice.session !== "off" && voice.shortcutRegistered && (
                  <span className="voice-shortcut"> · {MUTE_SHORTCUT_LABEL} mutes</span>
                )}
              </span>
            </div>
            <button type="submit" disabled={busy || detail?.conversation.removed === true}>
              {busy ? "…" : "Send"}
            </button>
          </div>
        </form>

        {/* What the microphone is hearing, as a guess in progress. Deliberately
            outside the conversation: a provisional transcript is not a message, and
            the service keeps the two in separate fields precisely so that nothing
            renders one as the other. */}
        {voiceSession !== null && voiceSession.provisional !== "" && (
          <p className="voice-provisional" aria-live="polite">
            <span className="visually-hidden">Hearing: </span>
            {voiceSession.provisional}
          </p>
        )}
        {/* The three owner-facing voice measurements the order names (§7, §18). Shown
            rather than only logged, because the unmute figure is a promise about his
            microphone and he should be able to see it. */}
        {voice.session !== "off" && <VoiceMeasurements timings={voiceTimings} />}
        {voiceNotice !== null && <div className="notice voice-notice">{voiceNotice}</div>}
        {voiceSession !== null && voiceSession.error !== null && (
          <div className="notice voice-notice">{voiceSession.error}</div>
        )}

        <footer className="signals">
          {costs !== null && (
            <span>
              Month to date ${costs.month_to_date_usd.toFixed(4)}
              {" · "}classification ${(costs.by_task_type["classification"] ?? 0).toFixed(4)}
              {!costs.complete &&
                ` · ${costs.uncosted_calls} call(s) with unestablished cost — this figure is what is known, not the whole`}
            </span>
          )}
          <span>
            {lastDisagreement === null
              ? "Val has not yet disagreed on the record."
              : `Val last disagreed ${new Date(lastDisagreement).toLocaleString()}.`}
          </span>
        </footer>
      </main>
    </div>
  );
}

// The last turn's timing, each figure labelled by where its clock started
// (13 September 2026): everything from Send on one line; the response call's
// own first-token time on another, never beside them as if comparable.
function TimingPanel(props: { report: TurnTimingReport }): React.JSX.Element {
  const lines = timingLines(props.report);
  return (
    <div
      className="timing"
      title="From Send: measured in this window from the moment the message was sent. Response call alone: measured by the gateway from the start of the final response call, after all work before it."
    >
      <p>{lines.fromSend}</p>
      {lines.responseCall !== null && <p>{lines.responseCall}</p>}
      {lines.visibility !== null && <p>{lines.visibility}</p>}
    </div>
  );
}

// The thread while a turn is in flight: the prior messages, his message, and
// Val's words as they arrive. Marked as in progress until the settled message
// replaces it; nothing here is presented as persisted.
function StreamingThread(props: {
  detail: ConversationDetail | null;
  streaming: Streaming;
}): React.JSX.Element {
  const { detail, streaming } = props;
  return (
    <div className="messages">
      {detail !== null && <h2>{detail.conversation.title}</h2>}
      {detail?.messages.map((message) => (
        <div key={message.id} className={`message ${message.role} ${isLive(message) ? "" : "withdrawn collapsed"}`}>
          <div className="speaker">{message.role === "user" ? "Lord Armand" : "Val"}</div>
          {isLive(message) ? (
            <>
              <div className="content">
                {message.role === "val" ? <Prose text={message.content} /> : message.content}
              </div>
              <Attachments attachments={message.attachments} />
            </>
          ) : (
            <div className="state-line">{userStateLine(message) ?? answerStateLine(message)}</div>
          )}
        </div>
      ))}
      <div className="message user">
        <div className="speaker">Lord Armand</div>
        <div className="content">{streaming.userContent}</div>
      </div>
      <div className="message val streaming" aria-live="polite">
        <div className="speaker">Val</div>
        {streaming.text === "" ? (
          streaming.stage === null ? (
            <div className="content pending" aria-label="Val is composing">…</div>
          ) : (
            <div className="content pending stage" title={PROGRESS_NOTE}>
              {STAGE_WORDS[streaming.stage]}
            </div>
          )
        ) : (
          <div className="content">
            <Prose text={streaming.text} />
          </div>
        )}
      </div>
    </div>
  );
}


// Owner ruling, 19 September 2026 (Track C §14). What was attached to a message,
// rendered from the bytes the house already holds. The classification shown is
// the one stated for THIS act — the same file attached again on a later turn is
// a different act with its own statement, and the thread says so rather than
// implying one class follows the file around.
// One image chosen in the composer, before anything is sent. Ephemeral client
// state: selecting a file writes nothing, and removing it before sending leaves
// no trace, because evidence begins at the successful send commit.
interface PendingAttachment {
  key: string;
  file: File;
  previewUrl: string;
  classification: AttachmentClassification;
}

async function asAttachmentInput(pending: PendingAttachment): Promise<AttachmentInput> {
  const buffer = await pending.file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return {
    filename: pending.file.name,
    content_base64: btoa(binary),
    classification: pending.classification,
  };
}

// VAL's answers may use a conservative Markdown subset; the thread renders it
// rather than showing the control syntax (owner defect report, 20 September
// 2026). Every piece of the message's own text becomes a React text node, so
// nothing here can inject markup or execute a script, and no link or image is
// rendered from model output. The stored message is untouched.
// The voice intervals the owner cares about — owner execution order, §7 and §18.
//
// Each is a difference between two moments this window observed, and each is shown
// **only once both ends exist**: an interval with one end is not a duration, and a
// dash says so rather than a zero pretending to be a measurement.
function VoiceMeasurements(props: { timings: VoiceTimings }): React.JSX.Element | null {
  const { timings } = props;
  const span = (from: number | null, to: number | null): string =>
    from === null || to === null ? "—" : `${Math.round(to - from)} ms`;
  const unmute = span(timings.unmuteGestureAt, timings.unmuteTrackLiveAt);
  const ready = span(timings.unmuteGestureAt, timings.unmuteFirstChunkAt);
  const audible = span(timings.speechEndAt, timings.firstAudibleAt);
  const silence = span(timings.bargeInAt, timings.silenceAt);
  if (unmute === "—" && ready === "—" && audible === "—" && silence === "—") return null;
  return (
    <p className="voice-measurements">
      <span title="From your unmute gesture to a live microphone track.">
        unmute → live {unmute}
      </span>
      <span title="From your unmute gesture to the first audio chunk actually accepted.">
        unmute → capturing {ready}
      </span>
      <span title="From the settled transcript to the first sound from the speakers in this window.">
        transcript → audible {audible}
      </span>
      <span title="From your barge-in to the playing buffer being stopped in this window.">
        barge-in → silence {silence}
      </span>
    </p>
  );
}

function Prose(props: { text: string }): React.JSX.Element {
  const spans = (parts: Inline[]): React.JSX.Element[] =>
    parts.map((span, index) => {
      const key = `${span.kind}-${index}`;
      if (span.kind === "bold") return <strong key={key}>{span.text}</strong>;
      if (span.kind === "italic") return <em key={key}>{span.text}</em>;
      if (span.kind === "code") return <code key={key}>{span.text}</code>;
      return <Fragment key={key}>{span.text}</Fragment>;
    });
  return (
    <>
      {parseMarkdown(props.text).map((block, index) => {
        const key = `${block.kind}-${index}`;
        if (block.kind === "heading") {
          const Tag = (["h3", "h4", "h5", "h6", "h6", "h6"][block.level - 1] ??
            "h6") as "h3" | "h4" | "h5" | "h6";
          return <Tag key={key}>{spans(block.spans)}</Tag>;
        }
        if (block.kind === "bullets") {
          return (
            <ul key={key}>
              {block.items.map((item, at) => (
                <li key={at}>{spans(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "numbers") {
          return (
            <ol key={key}>
              {block.items.map((item, at) => (
                <li key={at}>{spans(item)}</li>
              ))}
            </ol>
          );
        }
        return <p key={key}>{spans(block.spans)}</p>;
      })}
    </>
  );
}

function Thread(props: {
  detail: ConversationDetail;
  projects: ProjectView[];
  onRecorded: () => void;
  onConversationChanged: () => Promise<void>;
  onRefused: (message: string) => void;
}): React.JSX.Element {
  const { detail, projects, onRecorded, onConversationChanged, onRefused } = props;
  const transitions = detail.scope_transitions ?? [];
  return (
    <div className="messages">
      <ConversationHeader
        conversation={detail.conversation}
        projects={projects}
        onChanged={onConversationChanged}
        onRefused={onRefused}
      />
      {transitions
        .filter((transition) => transition.after_sequence === 0)
        .map((transition) => (
          <div key={transition.id} className="scope-transition">
            {transitionLine(transition, projects)}
          </div>
        ))}
      {detail.messages.map((message) => (
        <Fragment key={message.id}>
          <MessageBlock
            message={message}
            detail={detail}
            onRecorded={onRecorded}
            onRefused={onRefused}
          />
          {transitions
            .filter((transition) => transition.after_sequence === message.sequence)
            .map((transition) => (
              <div key={transition.id} className="scope-transition">
                {transitionLine(transition, projects)}
              </div>
            ))}
        </Fragment>
      ))}
    </div>
  );
}

function MessageBlock(props: {
  message: MessageView;
  detail: ConversationDetail;
  onRecorded: () => void;
  onRefused: (message: string) => void;
}): React.JSX.Element {
  const { message, detail, onRecorded, onRefused } = props;
  const blind = detail.blind_positions.filter((b) => b.message_id === message.id);
  const manual = detail.deliberations.filter(
    (d) => d.message_id === message.id && d.blind_position_id === null,
  );
  const events = detail.execution_events.filter((e) => e.message_id === message.id);
  const live = isLive(message);
  // Withdrawn exchanges are collapsed and inspectable (ruling, 12 September 2026).
  const [expanded, setExpanded] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const [explainRefusal, setExplainRefusal] = useState(false);
  const [busy, setBusy] = useState(false);
  const stateLine = userStateLine(message);
  const answerLine = answerStateLine(message);

  const act = async (run: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await run();
      onRecorded();
    } catch (failure) {
      onRefused(describeFailure(failure));
    } finally {
      setBusy(false);
    }
  };

  if (!live && !expanded) {
    return (
      <div className={`message ${message.role} withdrawn collapsed`}>
        <div className="speaker">{message.role === "user" ? "Lord Armand" : "Val"}</div>
        <div className="state-line">
          {stateLine ?? answerLine}{" "}
          <button className="inline-action" onClick={() => setExpanded(true)}>
            Show
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`message ${message.role} ${live ? "" : "withdrawn"}`}>
      <div className="speaker">{message.role === "user" ? "Lord Armand" : "Val"}</div>
      {stateLine !== null && (
        <div className="state-line">
          {stateLine}
          {message.state === "corrected" && (message.original_content ?? null) !== null && (
            <>
              {" "}
              <button className="inline-action" onClick={() => setShowOriginal(!showOriginal)}>
                {showOriginal ? "Hide original" : "View original"}
              </button>
            </>
          )}
          {!live && (
            <>
              {" "}
              <button className="inline-action" onClick={() => setExpanded(false)}>
                Hide
              </button>
            </>
          )}
        </div>
      )}
      {answerLine !== null && (
        <div className="state-line">
          {answerLine}
          {!live && (
            <>
              {" "}
              <button className="inline-action" onClick={() => setExpanded(false)}>
                Hide
              </button>
            </>
          )}
        </div>
      )}
      {showOriginal && (message.original_content ?? null) !== null && (
        <div className="original">
          <div className="note">Originally sent {new Date(message.created_at).toLocaleString()}:</div>
          <div className="content">{message.original_content}</div>
        </div>
      )}
      {editing ? (
        <div className="edit">
          <p className="note">{EDIT_EXPLANATION}</p>
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={3} autoFocus />
          <button
            disabled={busy || draft.trim() === "" || draft === message.content}
            onClick={() =>
              void act(async () => {
                await api.reviseMessage(message.id, draft);
                setEditing(false);
              })
            }
          >
            Save correction
          </button>
          <button onClick={() => setEditing(false)}>Cancel</button>
        </div>
      ) : (
        <>
          <div className="content">
            {message.role === "val" ? <Prose text={message.content} /> : message.content}
          </div>
          <Attachments attachments={message.attachments} />
        </>
      )}

      {blind.map((position) => {
        const resolution = resolutionOf(position, detail.deliberations);
        const display = describeDeliberation(position.classification, position, resolution);
        return (
          <div key={position.id} className={`deliberation ${display.contaminated ? "contaminated" : ""}`}>
            <div className="capture">{display.capture}</div>
            <div className="position">
              <strong>Her position:</strong> {display.position}
            </div>
            <div className="confidence">{display.confidence}</div>
            <div className="reasoning">{display.reasoning}</div>
            <div className="ordering">{display.ordering}</div>
            {display.strippedPreference !== null && (
              <div className="stripped">Withheld from the blind call: “{display.strippedPreference}”</div>
            )}
            <div className="outcome">{display.outcome}</div>
          </div>
        );
      })}

      {manual.map((deliberation) => (
        <div
          key={deliberation.id}
          className={`deliberation ${deliberation.ordering === "contaminated" ? "contaminated" : ""}`}
        >
          <div className="capture">marked {deliberation.classification} by {deliberation.classified_by}</div>
          <div className="position">
            <strong>Her position:</strong> {deliberation.position}
          </div>
          <div className="ordering">
            {deliberation.independently_formed
              ? "formed blind, before exposure to the stated preference"
              : "contaminated — the preference could not be separated; this position was NOT independently formed"}
          </div>
          <div className="outcome">{outcomeLabel(deliberation)}</div>
        </div>
      ))}

      {events.map((event) => (
        <div key={event.id} className="event">
          {event.event_type ?? "reaction"} — {event.subject}
          {event.reason !== null
            ? ` · ${event.reason} (${event.reason_source})`
            : ` · no reason given (${event.reason_source})`}
          {event.reaction !== null && ` · reaction: ${event.reaction}`}
        </div>
      ))}

      {live && message.role === "val" && (
        <JudgeControl detail={detail} message={message} onRecorded={onRecorded} />
      )}
      {live && message.role === "user" && (
        <MarkConsequentialControl detail={detail} message={message} onRecorded={onRecorded} />
      )}
      {message.role === "user" && live && !editing && (
        <div className="message-actions">
          {canEdit(message) ? (
            <button
              className="inline-action"
              onClick={() => {
                setDraft(message.content);
                setEditing(true);
              }}
            >
              Edit
            </button>
          ) : (
            (message.revision_refusal ?? null) !== null && (
              <button className="inline-action" onClick={() => setExplainRefusal(!explainRefusal)}>
                Why can't this be edited?
              </button>
            )
          )}
          {canRemove(message) && (
            <button
              className="inline-action"
              disabled={busy}
              onClick={() => {
                if (window.confirm(REMOVE_MESSAGE_CONFIRMATION)) {
                  void act(() => api.retractMessage(message.id));
                }
              }}
            >
              Remove
            </button>
          )}
          {explainRefusal && (message.revision_refusal ?? null) !== null && (
            <div className="note">{message.revision_refusal}</div>
          )}
        </div>
      )}
    </div>
  );
}

// Conversation management — ruling, 12 September 2026. Rename sets the
// presentation-class title. Archive hides the conversation from the default
// sidebar listing and nothing else: it still resumes, recalls and keeps every
// record; "Show archived" recovers it.
function ConversationHeader(props: {
  conversation: ConversationView;
  projects: ProjectView[];
  onChanged: () => Promise<void>;
  onRefused: (message: string) => void;
}): React.JSX.Element {
  const { conversation, projects, onChanged, onRefused } = props;
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(conversation.title);
  const [busy, setBusy] = useState(false);

  const act = async (run: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await run();
      await onChanged();
    } catch (failure) {
      onRefused(describeFailure(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="conversation-header">
      {renaming ? (
        <div className="rename">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter")
                void act(async () => {
                  await api.renameConversation(conversation.id, title);
                  setRenaming(false);
                });
              if (event.key === "Escape") setRenaming(false);
            }}
            autoFocus
          />
          <button
            disabled={busy || title.trim() === ""}
            onClick={() =>
              void act(async () => {
                await api.renameConversation(conversation.id, title);
                setRenaming(false);
              })
            }
          >
            Save
          </button>
          <button onClick={() => setRenaming(false)}>Cancel</button>
        </div>
      ) : (
        <h2>
          {conversation.title}
          {conversation.archived && <span className="archived-tag"> (archived)</span>}
          {conversation.removed === true && <span className="archived-tag"> (removed)</span>}
        </h2>
      )}
      <div className="conversation-actions">
        {!renaming && (
          <button
            className="inline-action"
            onClick={() => {
              setTitle(conversation.title);
              setRenaming(true);
            }}
          >
            Rename
          </button>
        )}
        <button
          className="inline-action"
          disabled={busy}
          title={
            conversation.archived
              ? "Show this conversation in the sidebar again."
              : "Hide from the sidebar. Val still remembers it; nothing is removed."
          }
          onClick={() =>
            void act(() =>
              conversation.archived
                ? api.unarchiveConversation(conversation.id)
                : api.archiveConversation(conversation.id),
            )
          }
        >
          {conversation.archived ? "Unarchive" : "Archive"}
        </button>
        <button
          className="inline-action"
          disabled={busy}
          title={
            conversation.removed === true
              ? "Return this conversation to active use."
              : "Withdraw from active use. Nothing is deleted."
          }
          onClick={() => {
            if (conversation.removed === true) {
              void act(() => api.reinstateConversation(conversation.id));
            } else if (window.confirm(REMOVE_CONVERSATION_CONFIRMATION)) {
              void act(() => api.removeConversation(conversation.id));
            }
          }}
        >
          {conversation.removed === true ? "Reinstate" : "Remove"}
        </button>
        {conversation.removed !== true && (
          <select
            className="move"
            value=""
            disabled={busy}
            aria-label="Move this conversation"
            onChange={(event) => {
              const target = event.target.value;
              if (target === "") return;
              const destination =
                target === "none"
                  ? { name: "no project", body: { no_project: true as const } }
                  : {
                      name: projects.find((project) => project.id === target)?.name ?? "that project",
                      body: { project_id: target },
                    };
              if (window.confirm(moveConfirmation(destination.name))) {
                void act(() => api.moveConversation(conversation.id, destination.body));
              }
            }}
          >
            <option value="">Move to…</option>
            {projects
              .filter((project) => project.id !== conversation.project_id)
              .map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            {conversation.project_id !== null && <option value="none">No project</option>}
          </select>
        )}
      </div>
    </div>
  );
}

// Ruled 7 September 2026: the classification review queue — the fifty. The
// same doctrine as the blind position, applied to Lord Armand: the queue item
// carries no verdict, and the verdict appears only after his label is stored.
export function ReviewPanel(props: { onRefused: (message: string) => void }): React.JSX.Element {
  const { onRefused } = props;
  const [queue, setQueue] = useState<QueuedExchangeView[]>([]);
  const [progress, setProgress] = useState<ReviewProgressView | null>(null);
  const [disagreements, setDisagreements] = useState<LabelledExchangeView[]>([]);
  const [revealed, setRevealed] = useState<LabelledExchangeView | null>(null);
  const [label, setLabel] = useState<HumanClassification | null>(null);
  const [determination, setDetermination] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setQueue(await api.reviewQueue());
      setProgress(await api.reviewProgress());
      setDisagreements(await api.reviewDisagreements());
    } catch (failure) {
      onRefused(describeFailure(failure));
    }
  }, [onRefused]);

  useEffect(() => {
    void load();
  }, [load]);

  const current = queue[0] ?? null;

  const commit = async () => {
    if (current === null || label === null || busy) return;
    if (label === "not_consequential" && determination === "") return;
    setBusy(true);
    try {
      const stored = await api.labelExchange({
        classification_id: current.classification_id,
        label,
        ...(label === "not_consequential" ? { exclusion_determination: determination } : {}),
      });
      setRevealed(stored);
      setLabel(null);
      setDetermination("");
      setQueue((items) => items.slice(1));
      setProgress(await api.reviewProgress());
      setDisagreements(await api.reviewDisagreements());
    } catch (failure) {
      onRefused(describeFailure(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="review">
      <h2>Review classifications</h2>
      {progress !== null && <p className="note">{progressLine(progress)}</p>}

      {revealed !== null ? (
        <div className="review-card">
          <p className="note">Your label is stored. The classifier said:</p>
          <p>
            <strong>{revealed.verdict}</strong>
            {revealed.hard_exclusion !== null && ` · hard exclusion: ${revealed.hard_exclusion}`}
          </p>
          <p>
            You said <strong>{revealed.label.label}</strong>
            {revealed.label.exclusion_determination !== null &&
              ` · ${determinationLabel(revealed.label.exclusion_determination)}`}
          </p>
          <p className={revealed.agreement === "agree" ? "" : "disagreement"}>
            {AGREEMENT_WORDS[revealed.agreement]}
          </p>
          <button onClick={() => setRevealed(null)}>Next</button>
        </div>
      ) : current === null ? (
        <p className="empty">Nothing awaiting a label.</p>
      ) : (
        <div className="review-card">
          <p className="note">
            {current.conversation_title} · {new Date(current.classified_at).toLocaleString()} ·{" "}
            {queue.length} awaiting
          </p>
          <div className="content">{current.content}</div>
          <p className="note">
            Apply the contract yourself: is a choice being made among alternatives, and does it
            bind later work? Check the hard exclusions first. The classifier&apos;s verdict is
            revealed only after you record your label.
          </p>
          <div className="review-choices">
            {(["consequential", "uncertain", "not_consequential"] as HumanClassification[]).map(
              (choice) => (
                <button
                  key={choice}
                  className={label === choice ? "selected" : ""}
                  onClick={() => {
                    setLabel(choice);
                    if (choice !== "not_consequential") setDetermination("");
                  }}
                >
                  {choice.replace(/_/g, " ")}
                </button>
              ),
            )}
          </div>
          {label === "not_consequential" && (
            <div className="review-determination">
              <p className="note">Second determination, required:</p>
              <select value={determination} onChange={(event) => setDetermination(event.target.value)}>
                <option value="">— choose —</option>
                {HARD_EXCLUSIONS.map((exclusion) => (
                  <option key={exclusion} value={exclusion}>
                    hard exclusion: {exclusion.replace(/_/g, " ")}
                  </option>
                ))}
                <option value={NONE_FAILS_INCLUSION_TEST}>
                  no hard exclusion — it fails the consequential inclusion test
                </option>
              </select>
            </div>
          )}
          <button
            onClick={() => void commit()}
            disabled={
              busy || label === null || (label === "not_consequential" && determination === "")
            }
          >
            Record label
          </button>
        </div>
      )}

      <h3>Disagreements</h3>
      {disagreements.length === 0 ? (
        <p className="empty">None recorded.</p>
      ) : (
        disagreements.map((item) => (
          <DisagreementCard key={item.classification_id} item={item} onRecorded={load} onRefused={onRefused} />
        ))
      )}
    </div>
  );
}

function DisagreementCard(props: {
  item: LabelledExchangeView;
  onRecorded: () => Promise<void>;
  onRefused: (message: string) => void;
}): React.JSX.Element {
  const { item, onRecorded, onRefused } = props;
  const [open, setOpen] = useState(false);
  const [conclusion, setConclusion] = useState<ReviewConclusion>("classifier_upheld_label_wrong");
  const [reason, setReason] = useState("");

  const record = async () => {
    if (reason.trim() === "") return;
    try {
      await api.reviewExchange({ classification_id: item.classification_id, conclusion, reason });
      setOpen(false);
      setReason("");
      await onRecorded();
    } catch (failure) {
      onRefused(describeFailure(failure));
    }
  };

  return (
    <div className={`review-card ${item.open_disagreement ? "open" : ""}`}>
      <div className="content">{item.content}</div>
      <p>
        You said <strong>{item.label.label}</strong>
        {item.label.exclusion_determination !== null &&
          ` · ${determinationLabel(item.label.exclusion_determination)}`}
        ; the classifier said <strong>{item.verdict}</strong>
        {item.hard_exclusion !== null && ` · hard exclusion: ${item.hard_exclusion}`}.
      </p>
      <p className="disagreement">{AGREEMENT_WORDS[item.agreement]}</p>
      {item.reviews.map((review) => (
        <p key={review.id} className="note">
          Review: {CONCLUSION_WORDS[review.conclusion]} — {review.reason}
          {review.tuning_state !== null && ` · ${review.tuning_state.replace(/_/g, " ")}`}
          {review.tuning_change !== null && ` · change: ${review.tuning_change}`}
        </p>
      ))}
      <p className="note">{item.open_disagreement ? "Open — not resolved by being viewed." : "Resolved."}</p>
      {!open ? (
        <button className="inline-action" onClick={() => setOpen(true)}>
          Record a review
        </button>
      ) : (
        <div className="judge">
          <select value={conclusion} onChange={(event) => setConclusion(event.target.value as ReviewConclusion)}>
            <option value="label_upheld_classifier_wrong">{CONCLUSION_WORDS.label_upheld_classifier_wrong}</option>
            <option value="classifier_upheld_label_wrong">{CONCLUSION_WORDS.classifier_upheld_label_wrong}</option>
            <option value="ambiguous_needs_ruling">{CONCLUSION_WORDS.ambiguous_needs_ruling}</option>
          </select>
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="why — in your own words" />
          <button onClick={() => void record()} disabled={reason.trim() === ""}>
            Record
          </button>
          <button onClick={() => setOpen(false)}>Cancel</button>
        </div>
      )}
    </div>
  );
}

// Ruled 7 September 2026: the smallest proper project-creation path. A name,
// create, select. The service derives the slug and refuses a taken name in
// words; the refusal is shown as received, never reworded into a guess.
function NewProjectControl(props: {
  onCreated: (project: ProjectView) => Promise<void>;
  onRefused: (message: string) => void;
}): React.JSX.Element {
  const { onCreated, onRefused } = props;
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    if (name.trim() === "" || busy) return;
    setBusy(true);
    try {
      const project = await api.createProject(name.trim());
      setName("");
      setOpen(false);
      await onCreated(project);
    } catch (failure) {
      onRefused(describeFailure(failure));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button className="inline-action" onClick={() => setOpen(true)}>
        New project
      </button>
    );
  }
  return (
    <div className="new-project">
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="project name"
        onKeyDown={(event) => {
          if (event.key === "Enter") void create();
        }}
        autoFocus
      />
      <button onClick={() => void create()} disabled={busy || name.trim() === ""}>
        Create
      </button>
      <button onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
}

function JudgeControl(props: {
  detail: ConversationDetail;
  message: MessageView;
  onRecorded: () => void;
}): React.JSX.Element {
  const { detail, message, onRecorded } = props;
  const [open, setOpen] = useState(false);
  const [eventType, setEventType] = useState("rejected");
  const [subject, setSubject] = useState("this reply");
  const [reason, setReason] = useState("");
  const [prompt, setPrompt] = useState<string | null>(null);

  const submit = async (declined: boolean) => {
    setPrompt(null);
    try {
      await api.recordEvent({
        conversation_id: detail.conversation.id,
        message_id: message.id,
        subject,
        event_type: eventType,
        ...(reason.trim() !== "" ? { reason } : {}),
        ...(declined ? { declined_to_give_reason: true } : {}),
      });
      setOpen(false);
      setReason("");
      onRecorded();
    } catch (failure) {
      if (
        failure instanceof ApiRefusal &&
        typeof failure.detail === "object" &&
        failure.detail !== null &&
        "reason_required" in failure.detail
      ) {
        // The WP-0.8 prompt, in place: the record is not written until the
        // question is answered or explicitly declined.
        const detail_ = failure.detail as { message?: unknown };
        setPrompt(typeof detail_.message === "string" ? detail_.message : String(failure.message));
      } else {
        setPrompt(describeFailure(failure));
      }
    }
  };

  if (!open) {
    return (
      <button className="inline-action" onClick={() => setOpen(true)}>
        Judge this
      </button>
    );
  }
  return (
    <div className="judge">
      <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
        <option value="accepted">accept</option>
        <option value="rejected">reject</option>
        <option value="revision_requested">request revision</option>
        <option value="corrected">correct</option>
      </select>
      <input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="what is being judged" />
      <textarea
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="why — in your own words"
        rows={2}
      />
      {prompt !== null && <div className="prompt">{prompt}</div>}
      <button onClick={() => void submit(false)}>Record</button>
      <button onClick={() => void submit(true)}>He declines to give a reason</button>
      <button onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
}

function MarkConsequentialControl(props: {
  detail: ConversationDetail;
  message: MessageView;
  onRecorded: () => void;
}): React.JSX.Element {
  const { detail, message, onRecorded } = props;
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState("");
  const [confidence, setConfidence] = useState<Confidence>("medium");
  const [reasoning, setReasoning] = useState("");
  const [outcome, setOutcome] = useState<Outcome>("held");
  const [whatChanged, setWhatChanged] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async () => {
    setProblem(null);
    try {
      await api.markConsequential({
        conversation_id: detail.conversation.id,
        message_id: message.id,
        position,
        confidence,
        reasoning,
        user_response: message.content,
        outcome,
        ...(outcome === "updated" ? { what_changed_her_mind: whatChanged } : {}),
      });
      setOpen(false);
      onRecorded();
    } catch (failure) {
      setProblem(describeFailure(failure));
    }
  };

  if (!open) {
    return (
      <button className="inline-action" onClick={() => setOpen(true)}>
        Mark consequential
      </button>
    );
  }
  return (
    <div className="mark">
      <p className="note">
        A retroactive record: the position below was not formed blind, and it will be recorded as
        contaminated — which is the truth of it.
      </p>
      <textarea
        value={position}
        onChange={(event) => setPosition(event.target.value)}
        placeholder="the position Val took"
        rows={2}
      />
      <select value={confidence} onChange={(event) => setConfidence(event.target.value as Confidence)}>
        <option value="high">high confidence</option>
        <option value="medium">medium confidence</option>
        <option value="low">low confidence</option>
      </select>
      <textarea
        value={reasoning}
        onChange={(event) => setReasoning(event.target.value)}
        placeholder="her reasoning, briefly"
        rows={2}
      />
      <select value={outcome} onChange={(event) => setOutcome(event.target.value as Outcome)}>
        <option value="held">she held</option>
        <option value="updated">she updated</option>
        <option value="overridden">Lord Armand overrode</option>
        <option value="agreed_from_start">agreed from the start</option>
      </select>
      {outcome === "updated" && (
        <textarea
          value={whatChanged}
          onChange={(event) => setWhatChanged(event.target.value)}
          placeholder="what changed her mind — required"
          rows={2}
        />
      )}
      {problem !== null && <div className="prompt">{problem}</div>}
      <button onClick={() => void submit()}>Record</button>
      <button onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
}