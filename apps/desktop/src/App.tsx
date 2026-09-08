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

import { useCallback, useEffect, useState } from "react";

import type {
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
} from "./api";
import { api, ApiRefusal, describeFailure, HARD_EXCLUSIONS, NONE_FAILS_INCLUSION_TEST } from "./api";
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

type Scope = { kind: "project"; project: ProjectView } | { kind: "none" } | { kind: "all" };

export function App(): React.JSX.Element {
  const [projects, setProjects] = useState<ProjectView[]>([]);
  const [scope, setScope] = useState<Scope>({ kind: "all" });
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
  const [busy, setBusy] = useState(false);
  // Whether archived rows are listed. Display scoping only — the flag carries
  // no evidentiary meaning (§2.1 amendment, 31 August 2026), and everything
  // outside the two listings is archive-blind.
  const [showArchived, setShowArchived] = useState(false);
  // Ruled 7 September 2026: the classification review queue lives beside the
  // conversation thread, never over it.
  const [view, setView] = useState<"conversation" | "review">("conversation");

  const refreshConversations = useCallback(
    async (at: Scope) => {
      const archived = showArchived ? { archived: true } : {};
      if (at.kind === "project") {
        setConversations(await api.conversations({ project_id: at.project.id, ...archived }));
      } else if (at.kind === "none") {
        setConversations(await api.conversations({ scope: "none", ...archived }));
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

  const chooseScope = useCallback(
    async (next: Scope) => {
      setScope(next);
      setDetail(null);
      setClarification(null);
      await refreshConversations(next);
    },
    [refreshConversations],
  );

  const send = useCallback(
    async (content: string, projectOverride?: string) => {
      if (content.trim() === "" || busy) return;
      setBusy(true);
      setNotice(null);
      setClarification(null);
      try {
        const outcome = await api.turn({
          content,
          ...(detail !== null ? { conversation_id: detail.conversation.id } : {}),
          ...(projectOverride !== undefined
            ? { project: projectOverride }
            : scope.kind === "project" && detail === null
              ? { project: scope.project.name }
              : {}),
          ...(scope.kind === "none" && detail === null ? { no_project: true } : {}),
        });
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
        await openConversation(outcome.conversation.id);
        await refreshConversations(scope);
        await refreshSignals();
      } catch (failure) {
        setNotice(describeFailure(failure));
      } finally {
        setBusy(false);
      }
    },
    [busy, detail, scope, openConversation, refreshConversations, refreshSignals],
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
                onClick={() => void chooseScope({ kind: "all" })}
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
                  onClick={() => void chooseScope({ kind: "project", project })}
                >
                  {project.name}
                  {project.archived && <span className="archived-tag"> (archived)</span>}
                </button>
              </li>
            ))}
            <li>
              <button
                className={scope.kind === "none" ? "selected" : ""}
                onClick={() => void chooseScope({ kind: "none" })}
              >
                No project
              </button>
            </li>
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
                  onClick={() => void openConversation(conversation.id)}
                >
                  {conversation.title}
                  {conversation.archived && <span className="archived-tag"> (archived)</span>}
                </button>
              </li>
            ))}
          </ul>
          <button
            className="new-conversation"
            onClick={() => {
              setView("conversation");
              setDetail(null);
            }}
          >
            New conversation
          </button>
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
            Show archived
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
        ) : detail === null ? (
          <p className="empty">
            {scope.kind === "project"
              ? `A new conversation in ${scope.project.name}.`
              : scope.kind === "none"
                ? "A new conversation, explicitly outside every project."
                : "Choose a conversation, or say something to start one."}
          </p>
        ) : (
          <Thread detail={detail} onRecorded={() => void openConversation(detail.conversation.id)} />
        )}

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

        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send(composer);
          }}
        >
          <textarea
            value={composer}
            onChange={(event) => setComposer(event.target.value)}
            placeholder="Say something to Val…"
            rows={3}
          />
          <button type="submit" disabled={busy}>
            {busy ? "…" : "Send"}
          </button>
        </form>

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

function Thread(props: {
  detail: ConversationDetail;
  onRecorded: () => void;
}): React.JSX.Element {
  const { detail, onRecorded } = props;
  return (
    <div className="messages">
      <h2>{detail.conversation.title}</h2>
      {detail.messages.map((message) => (
        <MessageBlock key={message.id} message={message} detail={detail} onRecorded={onRecorded} />
      ))}
    </div>
  );
}

function MessageBlock(props: {
  message: MessageView;
  detail: ConversationDetail;
  onRecorded: () => void;
}): React.JSX.Element {
  const { message, detail, onRecorded } = props;
  const blind = detail.blind_positions.filter((b) => b.message_id === message.id);
  const manual = detail.deliberations.filter(
    (d) => d.message_id === message.id && d.blind_position_id === null,
  );
  const events = detail.execution_events.filter((e) => e.message_id === message.id);
  return (
    <div className={`message ${message.role}`}>
      <div className="speaker">{message.role === "user" ? "Lord Armand" : "Val"}</div>
      <div className="content">{message.content}</div>

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

      {message.role === "val" && (
        <JudgeControl detail={detail} message={message} onRecorded={onRecorded} />
      )}
      {message.role === "user" && (
        <MarkConsequentialControl detail={detail} message={message} onRecorded={onRecorded} />
      )}
    </div>
  );
}

// Ruled 7 September 2026: the classification review queue — the fifty. The
// same doctrine as the blind position, applied to Lord Armand: the queue item
// carries no verdict, and the verdict appears only after his label is stored.
function ReviewPanel(props: { onRefused: (message: string) => void }): React.JSX.Element {
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