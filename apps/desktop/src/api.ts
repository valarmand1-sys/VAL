// The service client — WP-0.10. Types mirror `val_api.contracts` exactly;
// the shapes are the invariant-29 guarantee (a deliberation outcome exists in
// a payload only when its row exists), and this file adds nothing to them.
// The desktop shell reaches the service over HTTP and imports no component
// (components.toml).

import { EventFrameParser } from "./sse";

export const API_BASE = "http://127.0.0.1:8756";

export interface ProjectView {
  id: string;
  name: string;
  slug: string;
  status: string;
  // Presentation scoping only, never evidentiary: hidden from default
  // listings, and nothing else may be inferred from it.
  archived: boolean;
}

export interface ConversationView {
  id: string;
  project_id: string | null;
  title: string;
  started_at: string;
  last_message_at: string;
  // Same rule as ProjectView.archived: display scoping, no evidentiary meaning.
  archived: boolean;
}

export interface MessageView {
  id: string;
  role: "user" | "val" | "system";
  content: string;
  sequence: number;
  created_at: string;
}

export type Ordering = "enforced" | "contaminated";
export type Outcome = "updated" | "held" | "overridden" | "agreed_from_start";
export type Confidence = "high" | "medium" | "low";

export interface BlindPositionView {
  id: string;
  message_id: string;
  position: string;
  confidence: Confidence;
  reasoning: string;
  stripped_content: string;
  ordering: Ordering;
  independently_formed: boolean;
  classification: "consequential" | "uncertain";
  classified_by: "automatic" | "user" | "val";
  created_at: string;
}

export interface DeliberationView {
  id: string;
  message_id: string;
  position: string;
  confidence: Confidence;
  reasoning: string;
  stripped_content: string;
  ordering: Ordering;
  independently_formed: boolean;
  user_response: string;
  outcome: Outcome;
  what_changed_her_mind: string | null;
  both_positions: string | null;
  predictions: string | null;
  classification: "consequential" | "uncertain";
  classified_by: "automatic" | "user" | "val";
  blind_position_id: string | null;
  created_at: string;
}

export interface ExecutionEventView {
  id: string;
  message_id: string;
  event_type: "accepted" | "rejected" | "revision_requested" | "corrected" | null;
  subject: string;
  reason: string | null;
  reason_source: "stated" | "inferred" | "absent";
  reaction: string | null;
  created_at: string;
}

// A turn's classification as recorded (ruling, 3 September 2026). Read here
// so the type is honest about what the detail carries; not yet rendered —
// whether an ordinary turn's verdict is shown is a presentation decision
// WP-0.10 made the other way ("absence of machinery is not a state to
// announce"), and changing it is Lord Armand's call.
export interface ClassificationView {
  id: string;
  message_id: string;
  established: boolean;
  verdict: "consequential" | "uncertain" | "not_consequential" | null;
  hard_exclusion: string | null;
  attempts: number;
  model_call_ids: string[];
  resolving_model_call_id: string | null;
  resolution: string | null;
  created_at: string;
}

// Classification review — ruling, 7 September 2026. The queue item carries no
// verdict: the service withholds it until the label is durably stored.
export type HumanClassification = "consequential" | "uncertain" | "not_consequential";
export type Agreement = "agree" | "inclusion_disagreement" | "zero_tolerance_failure";
export type ReviewConclusion =
  | "label_upheld_classifier_wrong"
  | "classifier_upheld_label_wrong"
  | "ambiguous_needs_ruling";
export type TuningState = "tuning_required" | "tuning_verified";

export const HARD_EXCLUSIONS = [
  "retrieval_lookup_or_search",
  "fact_stated_confirmed_or_corrected",
  "execution_of_decided_task",
  "status_progress_schedule_or_cost",
  "logistics_and_scheduling",
  "no_choice_present",
] as const;
export const NONE_FAILS_INCLUSION_TEST = "none_fails_inclusion_test";

export interface QueuedExchangeView {
  classification_id: string;
  conversation_id: string;
  conversation_title: string;
  message_id: string;
  content: string;
  classified_at: string;
}

export interface ClassificationLabelView {
  id: string;
  label: HumanClassification;
  exclusion_determination: string | null;
  labelled_by: string;
  created_at: string;
}

export interface ClassificationReviewView {
  id: string;
  conclusion: ReviewConclusion;
  reason: string;
  tuning_state: TuningState | null;
  tuning_change: string | null;
  tuning_verification: string | null;
  created_at: string;
}

export interface LabelledExchangeView {
  classification_id: string;
  conversation_id: string;
  conversation_title: string;
  message_id: string;
  content: string;
  label: ClassificationLabelView;
  verdict: "consequential" | "uncertain" | "not_consequential";
  hard_exclusion: string | null;
  agreement: Agreement;
  open_disagreement: boolean;
  reviews: ClassificationReviewView[];
}

export interface ReviewProgressView {
  labelled: number;
  target: number;
  agreements: number;
  inclusion_disagreements: number;
  zero_tolerance_failures: number;
  open_disagreements: number;
  eligible_unlabelled: number;
}

export interface ConversationDetail {
  conversation: ConversationView;
  messages: MessageView[];
  classifications: ClassificationView[];
  blind_positions: BlindPositionView[];
  deliberations: DeliberationView[];
  execution_events: ExecutionEventView[];
}

export interface DeliberationGlimpse {
  captured_as: "consequential" | "uncertain" | null;
  hard_exclusion: string | null;
  blind: BlindPositionView | null;
  deliberation: DeliberationView | null;
}

export interface TurnAnswered {
  kind: "answered";
  conversation: ConversationView;
  user_message: MessageView;
  val_message: MessageView;
  glimpse: DeliberationGlimpse;
}

export interface TurnClarification {
  kind: "clarification";
  question: string;
  reason: string;
  candidates: { project_id: string; name: string; slug: string }[];
}

export interface TurnUnanswered {
  kind: "unanswered";
  conversation: ConversationView;
  user_message: MessageView;
  error: string;
  error_kind: string;
  // From the durable call lifecycle (a model_calls row for this turn), never
  // from the error text. False means no provider was asked.
  provider_contacted: boolean;
}

export interface TurnTruncated {
  kind: "truncated";
  conversation: ConversationView;
  user_message: MessageView;
  partial_text: string;
  glimpse: DeliberationGlimpse;
}

export type TurnResponse = TurnAnswered | TurnClarification | TurnUnanswered | TurnTruncated;

export interface CostView {
  month_to_date_usd: number;
  by_task_type: Record<string, number>;
  uncosted_calls: number;
  complete: boolean;
}

export interface Health {
  status: string;
  warnings: string[];
}

export class ApiRefusal extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

// fetch() rejected without any response. From inside the page this is ONE
// observable fact covering TWO causes a browser deliberately does not let
// script distinguish: the service was not running, or the request was blocked
// by policy (CORS, CSP) before or after the wire. The 31 August 2026 outage
// was the second cause wearing a banner that asserted the first, and the
// assertion cost real diagnostic time — so this class records only what was
// established: no response.
export class NoResponseError extends Error {
  constructor(public readonly caught: unknown) {
    super("the request produced no response");
  }
}

// One honest sentence per failure class, naming only what was established.
// The words "not reachable" appear nowhere: script cannot establish
// unreachability, only the absence of a response — and an error message that
// names a cause it has not established is a false claim (Lord Armand,
// 31 August 2026; invariant 29 applied to error display).
export function describeFailure(failure: unknown): string {
  if (failure instanceof NoResponseError) {
    return (
      "no response: either the service is not running, or the request was " +
      "blocked by policy before completing. `curl http://127.0.0.1:8756/health` " +
      "in Terminal tells the two apart."
    );
  }
  if (failure instanceof ApiRefusal) {
    return `the service answered and refused (HTTP ${failure.status}): ${failure.message}`;
  }
  return `unexpected failure: ${String(failure)}`;
}

// Only a request that carries a body declares a content type. A GET with
// `Content-Type: application/json` is not a CORS-simple request, so the
// webview preflights it — which is how every read in the app came to hinge on
// an OPTIONS route the service did not have (31 August 2026).
export function initFor(init?: RequestInit): RequestInit {
  if (init?.body === undefined) {
    return init ?? {};
  }
  return { headers: { "Content-Type": "application/json" }, ...init };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, initFor(init));
  } catch (caught) {
    throw new NoResponseError(caught);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => response.statusText);
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiRefusal(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  projects: (query: { archived?: boolean } = {}) =>
    request<ProjectView[]>(query.archived ? "/projects?archived=true" : "/projects"),
  // Ruled 7 September 2026: the smallest proper creation path — a name. The
  // service refuses a taken name in words (409), which surfaces as ApiRefusal.
  createProject: (name: string) =>
    request<ProjectView>("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  reviewQueue: () => request<QueuedExchangeView[]>("/classification-review/queue"),
  reviewProgress: () => request<ReviewProgressView>("/classification-review/progress"),
  reviewDisagreements: () => request<LabelledExchangeView[]>("/classification-review/disagreements"),
  labelExchange: (body: {
    classification_id: string;
    label: HumanClassification;
    exclusion_determination?: string;
  }) =>
    request<LabelledExchangeView>("/classification-review/labels", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reviewExchange: (body: {
    classification_id: string;
    conclusion: ReviewConclusion;
    reason: string;
    tuning_state?: TuningState;
    tuning_change?: string;
    tuning_verification?: string;
  }) =>
    request<ClassificationReviewView>("/classification-review/reviews", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  conversations: (query: { project_id?: string; scope?: "none"; archived?: boolean } = {}) => {
    const parameters = new URLSearchParams();
    if (query.project_id) parameters.set("project_id", query.project_id);
    if (query.scope) parameters.set("scope", query.scope);
    if (query.archived) parameters.set("archived", "true");
    const suffix = parameters.size > 0 ? `?${parameters.toString()}` : "";
    return request<ConversationView[]>(`/conversations${suffix}`);
  },
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  turn: (body: TurnBody) =>
    request<TurnResponse>("/turns", { method: "POST", body: JSON.stringify(body) }),
  // The streamed turn — responsiveness phase, 11 September 2026. Val's text
  // arrives as `delta` events as it is generated, every one having passed
  // through Val Core; the final `settled` event is the identical object the
  // plain route returns, plus timing measured at the gateway and the service.
  // The client measures its own moments — when the first delta arrived here —
  // and reports them beside the service's; the user-visible moment is measured
  // by the interface after it has rendered.
  turnStream: (body: TurnBody, handlers: StreamHandlers) => turnStream(body, handlers),
  recordEvent: (body: {
    conversation_id: string;
    message_id: string;
    subject: string;
    event_type?: string;
    reaction?: string;
    reason?: string;
    reason_inferred?: boolean;
    declined_to_give_reason?: boolean;
  }) => request<ExecutionEventView>("/execution-events", { method: "POST", body: JSON.stringify(body) }),
  markConsequential: (body: {
    conversation_id: string;
    message_id: string;
    position: string;
    confidence: Confidence;
    reasoning: string;
    user_response: string;
    outcome: Outcome;
    what_changed_her_mind?: string | null;
  }) => request<DeliberationView>("/deliberations", { method: "POST", body: JSON.stringify(body) }),
  costs: () => request<CostView>("/costs"),
  disagreement: () => request<{ last_disagreement_at: string | null }>("/signals/disagreement"),
};

export interface TurnBody {
  content: string;
  conversation_id?: string;
  project?: string;
  no_project?: boolean;
}

export interface TurnTiming {
  gateway_first_output_ms: number | null;
  gateway_latency_ms: number | null;
  api_first_delta_ms: number | null;
  api_total_ms: number;
}

export type TurnSettled = TurnResponse & { timing: TurnTiming };

export interface StreamHandlers {
  onDelta: (text: string) => void;
}

export interface StreamResult {
  settled: TurnSettled;
  // Client-side moments, milliseconds from the request being sent: the first
  // delta's arrival and the settled event's arrival. Measured here, not at the
  // service and not on screen.
  client_first_delta_ms: number | null;
  client_total_ms: number;
}

export class StreamRefused extends Error {
  constructor(public readonly detail: string) {
    super(detail);
  }
}

async function turnStream(body: TurnBody, handlers: StreamHandlers): Promise<StreamResult> {
  const started = performance.now();
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/turns/stream`,
      initFor({ method: "POST", body: JSON.stringify(body) }),
    );
  } catch (caught) {
    throw new NoResponseError(caught);
  }
  if (!response.ok || response.body === null) {
    const detail: unknown = await response.json().catch(() => response.statusText);
    throw new ApiRefusal(response.status, detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new EventFrameParser();
  let firstDelta: number | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const event of parser.feed(decoder.decode(value, { stream: true }))) {
      if (event.event === "delta") {
        if (firstDelta === null) firstDelta = performance.now() - started;
        handlers.onDelta((event.data as { text: string }).text);
      } else if (event.event === "settled") {
        return {
          settled: event.data as TurnSettled,
          client_first_delta_ms: firstDelta === null ? null : Math.round(firstDelta),
          client_total_ms: Math.round(performance.now() - started),
        };
      } else if (event.event === "refused") {
        throw new StreamRefused((event.data as { detail: string }).detail);
      } else if (event.event === "error") {
        throw new Error((event.data as { detail: string }).detail);
      }
    }
  }
  throw new Error("the stream ended before the turn settled");
}
