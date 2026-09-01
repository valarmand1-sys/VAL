// The service client — WP-0.10. Types mirror `val_api.contracts` exactly;
// the shapes are the invariant-29 guarantee (a deliberation outcome exists in
// a payload only when its row exists), and this file adds nothing to them.
// The desktop shell reaches the service over HTTP and imports no component
// (components.toml).

export const API_BASE = "http://127.0.0.1:8756";

export interface ProjectView {
  id: string;
  name: string;
  slug: string;
  status: string;
}

export interface ConversationView {
  id: string;
  project_id: string | null;
  title: string;
  started_at: string;
  last_message_at: string;
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

export interface ConversationDetail {
  conversation: ConversationView;
  messages: MessageView[];
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
  projects: () => request<ProjectView[]>("/projects"),
  conversations: (query: { project_id?: string; scope?: "none" } = {}) => {
    const parameters = new URLSearchParams();
    if (query.project_id) parameters.set("project_id", query.project_id);
    if (query.scope) parameters.set("scope", query.scope);
    const suffix = parameters.size > 0 ? `?${parameters.toString()}` : "";
    return request<ConversationView[]>(`/conversations${suffix}`);
  },
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  turn: (body: {
    content: string;
    conversation_id?: string;
    project?: string;
    no_project?: boolean;
  }) => request<TurnResponse>("/turns", { method: "POST", body: JSON.stringify(body) }),
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
