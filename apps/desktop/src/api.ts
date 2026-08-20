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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
