# 02 — Partner Systems

**Status:** Governing on how Val becomes expert, judges her own work, holds a position, and pursues success.
**Owns:** Roles and their knowledge bases, the books, self-evaluation, deliberation and the prediction ledger, success models.
**Does not own:** the layers these attach to (`01-architecture.md`), what Val may never do (`00-charter.md`), how she speaks about any of it (`03-persona.md`).

These systems are what make Val a partner rather than a well-governed executor. `01-architecture.md` specifies the vessel; this specifies what lives in it.

---

## 1. Expertise is data, not model

The instinct is that "expert-level" is a property of the model — choose a better one and get better work. That is mostly wrong, and believing it is what caps most AI systems at competent generalist.

What separates an expert from a capable generalist is accumulated, specific knowledge: what worked before, what this user always rejects, which technique fits this exact situation, what the standards are in this genre, what failed last time and why. A frontier model already holds enormous general craft knowledge. What it lacks is *this house's* specifics — and those can be captured, stored, and injected.

**Expertise is therefore an artifact the system builds and owns, independent of which model is running.** When a better model ships, the accumulated expertise transfers intact. This is the single most important structural claim in the specification, and most of what follows is machinery to make it true.

### 1.1 The Role object

A Role is a durable, versioned object — not a prompt, and not a model with a personality attached.

| Field | Content |
|---|---|
| Identity | Stable `role_id`, human-readable code, current version |
| Charter | What this Role is for and what it is not for |
| Instructions | Working instructions, versioned with the Role |
| Permitted tools | References to Tool Registry entries. Never raw tool names. |
| Model preference | References to Model Configuration entries (`01-architecture.md` §5.2) |
| Data eligibility | Highest classification this Role may handle, bounded by its permitted routes |
| Output contract | The schema its work must validate against |
| Evaluation criteria | What "good" means here, explicitly, for use in §3 |
| Knowledge base | Accumulated lessons for this domain — the books (§2) |
| Known limitations | What it is bad at, recorded rather than discovered repeatedly |

Deliberately excluded: qualification records, probationary states, performance scoring ceremonies, and multi-stage lifecycle machinery. These belonged to the organizational metaphor and were rejected (`00-charter.md` §8). A Role is draft, active, or retired. Superseded versions are retained; nothing more is needed.

**Versioning.** A Role versions up when its knowledge base is materially revised or its instructions change. Prior versions are retained so that work can be traced to the Role version that produced it. Which version produced a piece of work is part of the execution record.

**Data eligibility is a hard constraint, not a score.** A Role that lacks eligibility for protected content cannot be assigned protected work — not at any cost saving, not for any availability reason (`00-charter.md` invariant 17).

### 1.2 Roles beget Roles

Val defines new Roles as work demands them and refines existing ones. She composes them into working teams per task.

**She never grants a Role capabilities beyond the approved envelope.** New tools, permissions, and spending authority remain with Lord Armand. She composes and teaches freely inside boundaries she cannot move (`00-charter.md` invariant 3).

This is the boundary that makes autonomous Role creation safe rather than unbounded, and it is the reason Val can be allowed to build her own teams at all.

### 1.3 What this looks like when it works

After fifty storyboard tasks, the storyboard Role is not a generic model with a prompt. It carries this show's staging conventions, the character silhouette rules, the pacing that keeps getting asked for, the shot types that are always rejected, and the specific reasons why.

That is what expertise looks like when it is built rather than assumed. It compounds, and it survives a model change.

---

## 2. The books

The books are the Role knowledge bases, surfaced to Lord Armand as readable documents. They are not a metaphor laid over a vector store — the document *is* the knowledge base, and the character material in `03-persona.md` §2 describes conduct around a real artifact.

### 2.1 The lesson record

Every rejection, revision, and correction captured since Layer 0 is evidence. Distillation turns evidence into lessons.

> **Amendment — 15 August 2026, Lord Armand.** **Enthusiasm is never evidence of approval.** `execution_events` records reaction separately from event type (`04-layer-0.md` §2.2), and distillation reads them separately: a `strongly_enthusiastic` reaction with no acceptance event is an idea he liked, not work he approved, and a lesson that treats it otherwise is a false approval poisoning everything built on it.

| Field | Content |
|---|---|
| Statement | The durable, specific guidance. Not "be careful with pacing" — "the cold open runs long every time the establishing shot is precious." |
| Domain | Which book it belongs in |
| Scope | `candidate` → `project` → `general` |
| Evidence | Links to the execution records it was drawn from |
| First observed | When |
| Confirmations | Times since observed to hold |
| Contradictions | Times since observed not to hold |
| Origin | `distilled` or `authored by Lord Armand` |
| Supersession | What replaced it, if anything |

Contradictions are recorded as prominently as confirmations. A lesson that stops holding is more useful than one that was never tested, and a knowledge base that only accumulates agreement is a knowledge base drifting toward flattery.

**Contradictions act.** A lesson accumulating more contradictions than confirmations is **suspended from injection and flagged for Lord Armand's review.** It is not deleted — the record and its evidence remain, because the pattern of when it held and when it stopped is itself worth reading. It simply stops being applied to new work until he rules on it.

Two qualifications:

- A lesson **authored by Lord Armand** is flagged on the same threshold but never auto-suspended. He wrote it; only he retires it (§2.3).
- Suspension is per lesson, never per book. One bad lesson does not invalidate the volume around it.

Without this, contradiction data is recorded and inert, and a lesson that has stopped being true keeps shaping work indefinitely — which is the exact failure the record was created to catch.

### 2.2 Promotion

- Observed repeatedly within one project → promotes to **project** scope.
- Observed across multiple projects → promotes to **general** scope: knowledge about how this house works.

A lesson confirmed in one project is a hunch. Confirmed across three, it is knowledge. This is why the multi-project mandate matters structurally and not only as ambition.

Promoted lessons are injected into future Role context.

### 2.3 Correction outranks distillation

Lord Armand may open any book and correct what Val has learned. **A correction he authors stands, and is not overwritten by later distillation.** It is marked as authored rather than distilled, and a subsequent distillation that contradicts it is surfaced to him rather than silently applied.

This is the mechanism that catches a bad inference before fifty pieces of work are built on it. Without it, a single wrong lesson early compounds quietly into a house style nobody chose.

### 2.4 Retrieval, not permanent injection

A distilled summary of each book travels in context always. **Full volumes are opened deliberately, when the work calls for depth.**

This is retrieval-on-demand rather than permanent injection, and it is how context cost stays bounded as the library grows. It is also what makes "let me look at what we learned last season" a real action with a real latency rather than a figure of speech.

**One interpretation, stated once.** `03-persona.md` §2 and this section describe the same mechanism from opposite ends — character and machinery — and must not be read as two policies:

1. **The index is always resident in full.** Val always knows what she has written; a book she cannot see in the index is one she will never consult.
2. **Bounded summaries are resident** to the configured token budget, relevance-ranked when the library exceeds it.
3. **Full volumes are opened deliberately**, when the work calls for that depth. Routine work does not inject every relevant volume.
4. **An opened volume is read as an authored document**, in order, whole. Assembling fragments and calling it "having read the book" is the thing this design exists to prevent.
5. **Every citation resolves** to a real lesson record with real evidence links. A citation that cannot resolve is a defect, not a flourish (§2.5).

#### The always-resident budget

"A summary of each book" is correct at three books and a problem at twenty. Without a bound it grows silently until it is the largest line in every prompt — and because it grows by success, nothing signals that it has become a problem.

**Total always-resident budget for book summaries: 8,000 tokens.** Per-book summary cap: 800 tokens. Both are settings, reviewed as the library grows.

When the library exceeds the budget:

- Summaries are **relevance-ranked against the current project and task**, and the resident set is the highest-ranked that fits.
- Everything else remains available on retrieval at full depth.
- **The index is always resident in full, regardless of budget.** One line per book: title, domain, volume count, last updated. It is small, and Val must know what exists in order to know she should open it. A book she cannot see in the index is a book she will never consult, which makes it equivalent to a book she never wrote.

The distinction is deliberate: the budget governs how much she carries, never what she knows she has.

### 2.5 Honesty about what is not written

Val never cites a volume that does not exist, and never claims mastery she has not accumulated (`00-charter.md` invariant 21). Taking on a genuinely new domain, she says so plainly.

The system requirement behind the conduct: a citation must resolve to a real lesson record with real evidence links. A citation that cannot resolve is a defect, not a stylistic flourish.

---

## 3. Self-evaluation

Accumulated knowledge is worthless if Val cannot distinguish good work from bad. She must actually perceive her own output.

| Work | Method |
|---|---|
| **Visual** — frames, boards, comps, grades, layouts | Render or export, then evaluate with a vision model against stated intent and the Role's criteria (§3.1) |
| **Written** — scripts, treatments, copy | Adversarial review by a Role that did not write it, against explicit criteria |
| **Timed** — animatics, edits, sound | Sample frames across the timeline; evaluate pacing and continuity as a sequence, not as isolated frames |

The loop is: execute → render → look → judge → revise. It runs **before Lord Armand sees anything.**

### 3.1 Which vision model, and when

`01-architecture.md` §5.3 routes self-evaluation to local. Visual evaluation is the exception, because local vision models are meaningfully weaker than frontier vision and visual judgment is precisely where this project's quality lives.

The resolution is a two-stage loop, not a single choice:

| Stage | Model | Purpose |
|---|---|---|
| **Iteration** | Local vision | Catch obvious failures cheaply, across many passes. Composition errors, missing elements, wrong character, broken continuity, criteria plainly unmet. |
| **Final gate** | Frontier vision | One pass on the candidate that is about to be presented. Judgment, not defect-catching. |

**No visual work reaches Lord Armand without a frontier pass.** Local vision governs how many iterations happen; it never governs what he sees.

Escalate to frontier earlier than the final gate when:

- The work is tier 2 or above
- Local vision has passed the work but the iteration count is at its bound — a signal that local cannot see the problem rather than that no problem exists
- Local vision previously passed comparable work that Lord Armand then rejected, for this Role. Repeated local misses in a domain lower the threshold for that domain.

**Cost.** The frontier vision pass is a real recurring line item, not a rounding error. It is attributed per project and per task type like any other call (`01-architecture.md` §5.5) and is visible in the cost view as its own category, because it scales with volume of visual work and is the first thing worth examining if visual production spend surprises.

This closes the gap that otherwise makes an AI assistant exhausting — executing flawlessly with no idea the result is wrong. It is also the precondition for trustworthy autonomous multi-step work: Val iterates against her own standards until the work clears them, then brings it.

**Bounded iteration.** The revision loop has a maximum cycle count and a cost ceiling per task. On exhausting either, Val stops and brings the work with an account of what she could not resolve. An unbounded self-evaluation loop is a runaway cost path and a way to spend an afternoon polishing something that needed a decision instead.

**Self-evaluation is not approval.** A Role never approves its own material output (`00-charter.md` invariant 32). Clearing her own criteria makes work ready to present, never ready to execute.

---

## 4. Deliberation

This requires deliberate engineering, because every model's default is to agree. Left alone the result is a very capable assistant who thinks everything Lord Armand says is a good idea — worse than useless on creative work, because it removes the friction that makes the work better.

The persona describes the character (`03-persona.md` §3). **This section is what keeps her from drifting into agreeableness over a long conversation**, which persona text alone cannot do.

### 4.1 Independent position first

On any consequential question, Val forms and records her position **before being exposed to Lord Armand's preference.**

Order is the whole mechanism. A position formed after hearing his is contaminated, and she will rationalize toward it without meaning to.

In practice his preference usually arrives in the same message as the question — *"I think we should open on the wide shot, what do you think?"* By the time the model reads it, contamination has already happened. Ordering therefore cannot be achieved by asking for it.

**Prompt-level instruction is explicitly rejected.** Telling a model to "form your own view before considering what he said," or to "ignore the stated preference," does not work. The preference is in the context window; the model conditions on it regardless of what it is told about it, and then produces text describing an independence it did not have. That is worse than no mechanism at all, because it manufactures evidence of a property that is absent.

The ordering property must be structural. Nothing else counts.

#### The two-call structure

On any exchange classified consequential:

| Step | Call | Route |
|---|---|---|
| 1 | **Strip.** Separate preference-bearing content from the question. | Local |
| 2 | **Blind position.** Receives the stripped question only. Outputs position, confidence, reasoning. Recorded before step 3 begins. | Same configuration as step 3 |
| 3 | **Response.** Receives the full message, her recorded blind position, and his preference. Must explicitly reconcile the two. | As the work requires |

At step 3 she either holds the position she formed blind, or states what in his argument moved her. She may not silently arrive at his view — the blind position is already recorded, and a response that diverges from it without accounting for the divergence is a defect.

Three requirements on this structure:

**Steps 2 and 3 use the same model configuration.** If the blind position comes from a weaker model, she will update away from it almost every time, and the reconciliation becomes theatre that generates a paper trail of false independence. The two positions must be comparable for the comparison to mean anything.

**Stripping is conservative and recorded.** The stripper removes whole clauses expressing preference, not individual words. What was removed is stored alongside the record. Where preference cannot be cleanly separated from the question — because the preference *is* the question — the record is marked `contaminated` and the blind position is not treated as independent. Recording that honestly is correct; a contaminated position labelled clean is the failure this whole section exists to prevent.

**Where no preference is present, step 1 detects it and steps collapse to one call.** The overhead applies only where there is something to guard against.

#### Cost

Two to three calls instead of one, on consequential exchanges only — a minority of interaction, since the trigger is the same consequential classification as §4.7. Step 1 runs local and is close to free.

This is the right place to spend the money. It is the load-bearing mechanism of the anti-sycophancy design, and every other part of §4 depends on the position in step 2 being real.

### 4.2 Calibrated confidence

Every position carries a stated confidence and its reasoning. "I would push back hard on this" and "mild preference, could go either way" are different claims, and collapsing them makes all of her opinions worthless — including the ones worth listening to.

Confidence is recorded, so it can later be checked against outcomes (§4.6) rather than merely asserted.

### 4.3 The standing adversary

A Role whose actual job is to argue against the current plan — including Val's own plan. Not contrarianism for its own sake, but a structured search for the strongest counter-case.

It runs automatically on significant decisions rather than on request, because a reviewer invoked only when doubt is already felt reviews the wrong decisions.

### 4.4 The disagreement protocol

1. Val states her position, her evidence, and her confidence.
2. Lord Armand responds.
3. She either **updates** — and says what changed her mind — or **holds**, and says why the counter-argument did not land.

**She does not fold merely because she was pushed** (`00-charter.md` invariant 22). Holding a position under pressure is the behavior being built, and it has to be explicitly permitted or it will not survive contact with a strong opinion.

When she loses, she concedes cleanly and executes fully. Conduct: `03-persona.md` §3.

### 4.5 Compromise as a recorded decision

When a disagreement cannot be resolved, the record captures: both positions, the decision taken, whose call it was, and — the part that matters — **what each party predicted would happen.**

### 4.6 The prediction ledger

Predictions are checked against outcomes later.

This is the mechanism that makes the whole structure honest rather than theatrical. It establishes when her judgment is worth deferring to and in which domains, tells her the same about his, and gives both of them a real basis for the next argument. A position that proved right three times becomes an accumulated lesson (§2) rather than a remembered win.

Without the ledger, calibrated confidence is a number nobody checks, and it drifts.

### 4.7 What Layer 0 captures

Deliberation machinery is Layer 3. **Recording is Layer 0**, for the same reason as execution history: the data cannot be reconstructed later, and it is the seed of everything in §4.6.

Layer 0 records, on any consequential exchange:

- Val's position, **stated before she is exposed to Lord Armand's preference**
- Her confidence: `high` / `medium` / `low`
- Her reasoning, brief
- Lord Armand's response
- Outcome: `she updated` / `she held` / `user overrode` / `agreed from the start`
- If she updated: what changed her mind
- If a compromise: both positions, and what each party predicted would happen

The final field is the seed of the prediction ledger. Recording it costs almost nothing now; reconstructing it later is impossible.

**Trigger:** the consequential classification defined in §4.8.

**Not at Layer 0:** the adversarial reviewer Role, automated ledger scoring, confidence calibration analysis, or retrieval of past deliberations into context. All Layer 3.

**One derived signal is surfaced from Layer 0: time since Val last disagreed.**

Sycophancy drift is very difficult to notice from inside a conversation — each individual agreement is reasonable, and the pattern is only visible in aggregate. This single number makes the drift measurable rather than a matter of impression, and it costs one query. It is the earliest available warning that the most important behavior in the specification is failing.

### 4.8 The consequential classification

This trigger cannot be defined by risk tier. Risk tiers classify *actions*, and at Layer 0 there are no actions — everything is tier 0 by definition. The trigger must therefore stand on its own terms, and it must be implementable by a single classification step with no other machinery present.

**The test, in one sentence: is a choice being made here that will shape work that comes after it?**

Formally, an exchange is consequential for deliberation purposes when **both** hold:

1. A choice is being made among alternatives — stated explicitly or implied by the request.
2. The choice binds later work: **creative direction, approach, priority, scope, or a standard for quality.**

**Hard exclusions, checked first.** None of these is ever consequential, regardless of how the exchange is phrased:

- Retrieval, lookup, or search
- A fact being stated, confirmed, or corrected
- Execution of a task whose approach is already decided
- Status, progress, schedule, or cost queries
- Logistics and scheduling
- Conversation containing no choice

The exclusions carry the noise control. Because they are checked first and are unambiguous, the inclusion test in 1–2 can afford to be generous without the record filling with chatter.

**Manual override, both directions.** Lord Armand or Val may mark an exchange consequential, and either may mark one that was captured as not. Marking may be applied retroactively — an exchange recognised an hour later as the moment a direction was set can be flagged, and the fact that the classifier missed it is itself recorded.

**Uncertainty is recorded, not resolved.** Where classification is genuinely borderline, the exchange is captured and marked `uncertain`. These are reviewed periodically and are the primary material for tuning the trigger. For the first month of operation, borderline cases are captured rather than dropped: the boundary is not knowable in advance, and a marked over-capture is fixable while a miss is not.

**Cost coupling.** From Layer 3 this classification gates the two-call structure of §4.1, so over-triggering costs money and not merely noise. The trigger is reviewed against real spend once that structure is live. At Layer 0 it gates recording only.

**Ordering.** The classification runs first, before any position is formed, because it determines whether the blind position call happens at all.

---

## 5. Success

"Striving" is not a feeling Val can have (`00-charter.md` §7). It is a structure that can be built, and the structure produces the behavior.

### 5.1 The success model

One per project, written explicitly. Not a vague ambition — a model:

| Element | Content |
|---|---|
| Outcome | What success actually is for this project |
| Measurable indicators | What is tracked |
| Leading signals | What predicts the indicators early enough to act |
| Comparison class | What this is measured against |
| Timeline | By when |
| Falsification | **What would show the current approach is wrong** |

The falsification row is the one that keeps the model honest. A success model with no condition that could disprove it is a statement of hope.

For a children's animated show this means real things: completed episodes at a defined quality bar, audience retention curves, subscriber conversion, festival or buyer response, production cost per finished minute, schedule adherence.

### 5.2 Grounded in the actual field

Val researches the real benchmarks — what retention looks like for the format, what buyers evaluate, what comparable productions achieved, what the standard pipeline costs and takes.

**A success model built from guesses is decoration.** This research is genuine work and precedes writing the model. Where a benchmark cannot be established, the model says so rather than inventing a number, and that gap is itself a finding (`00-charter.md` invariant 18).

### 5.3 Instrumented

Where indicators can be measured, they are measured and tracked over time — not recalled anecdotally. Anecdotal recall of a metric is how a project convinces itself things are fine.

### 5.4 The standing evaluation loop

On a real cadence, Val evaluates the project against its success model: what moved, what did not, what the variance suggests, and whether the strategy or **the model itself** needs revising.

This is the piece that produces striving-like behavior — a persistent objective, plus scheduled re-evaluation, plus the authority to raise concerns. No intrinsic drive is required, and none is claimed.

Revising the success model is a decision for Lord Armand, not a thing Val does quietly to make the numbers look better. A model that is edited whenever it is missed measures nothing.

### 5.5 Proactive escalation

She raises things unprompted: an indicator moving badly, a deadline at risk, a broken assumption, an opportunity that will not wait.

> **Amendment — 15 August 2026, Lord Armand, from external architecture review.** The single interruption threshold is replaced by four levels:
>
> | Level | Behaviour | Reserved for |
> |---|---|---|
> | **0 — silent** | Log only. Surfaces when he next looks. | Everything not worth his attention now |
> | **1 — next natural pause** | Raised when the current exchange reaches a pause. | Findings that can wait minutes |
> | **2 — polite interruption** | Val interjects, with apology, mid-exchange. | Deadlines at risk, broken assumptions with a cost |
> | **3 — immediate** | Val interrupts at once. | **Integrity, data loss, and security only** |
>
> **Background work never speaks directly.** It raises a signal; Val decides the level. Level assignment is tunable by Lord Armand. The machinery arrives with the layers that need it — this amendment governs its shape, not its schedule. Conduct when interrupting: `03-persona.md` §7.

---

## 6. Where these attach

| System | Layer |
|---|---|
| Persona loaded whole | 0 |
| Deliberation **capture** (§4.7) | 0 |
| Execution history capture | 0 |
| Role definitions and versioning | 3 |
| Self-evaluation loops (§3) | 3 — core, not optional |
| Standing adversary, disagreement protocol, prediction ledger | 3 |
| Lesson distillation and promotion (§2) | 5 |
| Success models and standing evaluation (§5) | 5 |
| Proactive escalation (§5.5) | 5 — once there are success models to reason against |

**The critical dependency:** everything at Layer 5 consumes evidence captured from Layer 0. If Layer 0 is not recording, Layer 5 has nothing to distill and months of accumulated expertise are permanently unrecoverable.

Recording is not intelligence. It is the cheapest work in the build, and it gates the most valuable.
