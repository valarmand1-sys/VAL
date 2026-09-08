# Val — Layer 0 operating briefing

**Validity boundary.** As of commit `284e1c1` on the `master` branch, 7 September 2026, 18:25 Central time. Counts are read from the live PostgreSQL store at that moment. The live desktop service is running the code of commit `b6d5c32` plus documentation-only changes since. Anything after this timestamp is not reflected here.

**Who this is for.** A reader with no access to the repository, the code, the database, or the app, and no memory of the governing documents. Everything needed is reproduced here. Where the governing text matters, the governing sentence is quoted.

**Status vocabulary used in this briefing.** The project's own documents use "demonstrated, not asserted" as the standard, and its evidence index marks items PASS, BLOCKED, or NOT RUN. The five-word ladder below is not defined in the governing documents; it is defined here and used consistently:

- **implemented** — the code exists and its automated tests pass. Scripted-provider tests prove orchestration, never operational behaviour.
- **demonstrated** — shown working end to end against a real provider and a real database at least once, with durable evidence. A demonstration in a scratch database is a demonstration of the mechanism, not gate evidence.
- **operational evidence accumulating** — the mechanism is deployed and rows are appearing from Joseph's real use in the live store.
- **operational acceptance pending** — the mechanism works and evidence exists, but a review, count, or sign-off that the criterion names has not yet been done.
- **formally complete** — the criterion is met and recorded as met.

The Layer 0 baseline states the standard once: "every work package's acceptance criteria met and demonstrated, not asserted. Compiling is not completion. Passing unit tests alone is not completion."

---

## 1. The Layer 0 closing gate, exactly

The governing sentence: "Layer 0 is complete when all of the following hold simultaneously, demonstrated in one session:" followed by seven numbered points, then: "Points 4 through 7 are the gate. Points 1 through 3 are what makes the layer pleasant to use; 4 through 7 are what makes the next five layers possible."

Three rulings modify how the points are read today, all recorded in the baseline:

- 3 September 2026: point 5 restarts from zero, because the classifier had never delivered a parseable verdict on a real consequential exchange before that date; the fifty hand-labelled exchanges restart from zero; points 4, 6, 7 and the real conversations behind 1 to 3 keep their evidence.
- 7 September 2026: "A contaminated blind-position record never counts as evidence that ordering was enforced merely because a blind row exists." Point 5 uses only rows that record enforced ordering.
- 7 September 2026: the pause on creative work is lifted; "No conversation held in the paused interval is gate evidence for classification or deliberation." The paused interval is 3 to 7 September.

### Point 1 — "A real conversation, conducted through the interface, with no developer tooling."

- **Why it exists.** Layer 0 delivers a text conversation with a persistent, project-aware assistant, and the interface must support daily use without a terminal, a database client, or log tailing. The related work-package criterion: "A full day of real work conducted entirely through it, with no terminal, no database client, no log tailing."
- **Evidence.** A conversation in the live store whose every message was sent through the Val desktop app.
- **Measured.** By the existence of that conversation and by Joseph's own account of having worked a full day through the app. Nothing in the store records "a full day"; that judgement is his.
- **Current state.** Implemented. Operational evidence accumulating. One live conversation exists, 44 messages, sent through the app on 31 August and 3 September. Whether a "full day of real work" has yet been completed entirely through the app is not recorded anywhere and is Joseph's call to state. Operational acceptance pending on that statement.
- **Old evidence.** Counts. The August demonstration conversations are archived from listings but remain cited gate evidence; they were made partly through developer tooling, so the point-1 conversation of record is the one in the final session.
- **Remains.** The full day through the app, and the final session itself, which is this point by definition.
- **Natural or action.** Natural: using the app.
- **In the final session.** Yes. The final session is a real conversation through the app.

### Point 2 — "Attributed to a project, with resolution deterministic and ambiguity surfaced rather than guessed."

- **Why it exists.** Every exchange must be attributable to a project or explicitly to none; project scope drives recall and cost attribution; no model output may decide scope; an ambiguous reference must produce a question, never a guess.
- **Evidence.** The conversation's stored project, resolved from what Joseph explicitly stated; a demonstrated question when a name matches two projects.
- **Measured.** The conversation row's project attribution, and the recorded ambiguity behaviour.
- **Current state.** Implemented and demonstrated in the August acceptance runs with real providers, including the ambiguity question. **But note the live store today:** the only live conversation is recorded as explicitly no project, and there are zero live projects; all seven projects in the store are archived demonstration fixtures. A gate-session conversation must be attributed to a real project, and **the app has no way to create a project** — it can only select among projects that already exist. Creating the first real project is therefore NOT CURRENTLY USER-ACCESSIBLE; it needs a decision on the project's name and a developer insert, or a ruling to add project creation to the app.
- **Old evidence.** Counts for the mechanism. It does not supply a project for the final session.
- **Remains.** A real project to attribute the session to; then the session.
- **Natural or action.** Requires an action: deciding the project and having it created.
- **In the final session.** Yes: the session conversation must be attributed to a project and, to show ambiguity surfaced, at least one ambiguous reference should be made and answered with a question.

### Point 3 — "Persisted across a full restart of application and database, resuming with history intact."

- **Why it exists.** PostgreSQL is the sole authoritative store; a conversation must outlive the process and the database restart.
- **Evidence.** A conversation continued after both the desktop service and PostgreSQL were stopped and started, with history intact.
- **Measured.** By doing it and reading the conversation afterwards.
- **Current state.** Implemented and demonstrated in the WP-0.7 live acceptance in August against the live store. Operational: the service has been restarted several times since, and the live conversation resumed each time; the database has not been deliberately restarted mid-conversation since August.
- **Old evidence.** Counts for the mechanism; the final session must show it again.
- **Remains.** The restart inside the final session.
- **Natural or action.** Requires an action: stopping and starting the service and the database is done from a terminal, or by Claude Code on instruction. It is not done from inside the app.
- **In the final session.** Yes.

### Point 4 — "With `execution_events` populating — acceptances, rejections, revisions, corrections, each with its reason and `reason_source`."

- **Why it exists.** Execution history is captured from Layer 0 because it cannot be backfilled; every acceptance, rejection, revision request, and correction is recorded with why, and the record says whether the reason was stated by Joseph, inferred by Val, or absent.
- **Evidence.** Rows in the execution-events table. The work-package criteria add: "Accept, reject, request revision, and correct — one of each in real use — and confirm four rows with correct types"; "A rejection without a stated reason prompts for one. Declining to give a reason records reason_source = absent rather than fabricating one"; and "reason_source correctly distinguishes stated from inferred across a sample of twenty real events, checked by hand."
- **Measured.** Row counts by event type; the reason prompt behaviour; a hand-check of twenty real events.
- **Current state.** Implemented; the prompt behaviour is demonstrated; operational evidence accumulating.

  | Event type | Live rows | Reason source |
  |---|---|---|
  | accepted | 14 | all stated |
  | rejected | 3 | all stated |
  | revision_requested | 1 | stated |
  | corrected | 0 | none yet |

  Eighteen real events exist. Two things remain before the criterion is met: no `corrected` event has ever been recorded, and the twenty-event hand-check has not been done or recorded. On the hand-check, note that the app can only produce `stated` or `absent`: the "Val inferred the reason" path exists in the service but the app offers no control for it, so at Layer 0 the twenty-event check will find only stated and absent.
- **Old evidence.** Counts. The 3 September ruling left point 4 untouched.
- **Remains.** At least one correction judged in real use; at least twenty events in total; the hand-check, recorded as done.
- **Natural or action.** Judging is natural whenever a reply deserves it; the correction and the hand-check require deliberate acts.
- **In the final session.** Yes: the session must show events populating, which in practice means judging at least one reply during the session.

### Point 5 — "With `deliberations` populating on consequential exchanges, ordering enforced and demonstrable from the logged blind-call payload."

- **Why it exists.** This is the anti-sycophancy mechanism's evidence: on an exchange where a choice is being made that binds later work, Val's position must be formed before she sees Joseph's preference, recorded, and then reconciled. Without the ordering guarantee the records are contaminated by construction and would seed later layers with exactly the data the mechanism exists to exclude.
- **Evidence.** A blind-position row whose ordering is recorded as enforced, linked to a deliberations row carrying an outcome, and the logged payload of the blind call showing no preference-bearing content and no framing that presupposes a prior position.
- **Measured.** Rows in the two tables where ordering is enforced; the service's log line "blind position payload" and its companion "blind position withheld" for the same turn.
- **Current state.** Implemented. Demonstrated against the real provider in a scratch database on 3 and 7 September, including enforced ordering, the durable row before the response call, the reconciliation envelope, and outcomes held, updated, and agreed from the start. **Live count: zero blind positions, zero deliberations, zero classifications.** The count restarted at zero on 3 September; the pause ended on 7 September; no live turn has been sent since the repaired service was deployed. Operational evidence accumulating, from a base of nothing.
- **Old evidence.** None exists. Before 3 September the classifier had never delivered a parseable verdict on a real consequential exchange, so the machinery had never run in real use.
- **Remains.** Real consequential exchanges with a separable preference, occurring naturally, until enforced rows exist and the outcomes have been seen in real use; the work-package criterion adds "outcome populates correctly across all four values in real use", and the fourth value, overridden, is manual only.
- **Natural or action.** Natural through use, but only through the kind of exchange described in section 3C. Nothing is to be manufactured.
- **In the final session.** Yes: the session must contain at least one consequential exchange that produces an enforced deliberation, and the logged payload for it must be inspectable.

### Point 6 — "With `model_calls` populating on every call, cost and project and task type present, and zero uncosted calls."

- **Why it exists.** Per-call cost attribution is captured from Layer 0 and cannot be backfilled; the budget ceiling is enforced before a call, never reported after; a call with no row or a false zero cost is the failure this guards against.
- **Evidence.** A model-calls row for every provider call, with cost, project attribution, and task type. The work-package criterion: "Every call writes a model_calls row with cost, project, and task type populated. Zero calls without a row — verified by comparing provider dashboards against the table for a day of real use."
- **Measured.** The accounting view's count of uncosted calls for the month, and the dashboard comparison.
- **Current state.** Implemented; operational evidence accumulating. 88 rows all time. This month the accounting view reports zero uncosted calls. Twenty rows all time record a provider failure whose cost the provider never stated; they are recorded as unknown cost and settled at the reserved maximum, which is the doctrine, not a gap. The dashboard-versus-table comparison for a day of real use has never been done; the evidence index lists it as NOT RUN.
- **Old evidence.** Counts, including the failed classification calls of August and early September, which are costed honestly.
- **Remains.** The day-of-real-use dashboard comparison.
- **Natural or action.** Rows accumulate naturally; the comparison is a review in which Joseph reads the provider console figure, Claude Code produces the table figure for the same day.
- **In the final session.** Yes: every call in the session must have a row, and the session's calls are the natural sample.

### Point 7 — "And a verified restore from backup — restored to a scratch instance, row counts and referential integrity checked, capture tables continuous."

- **Why it exists.** "A backup never restored is not a backup." The authoritative store is backed up off-machine and encrypted, and restores are verified.
- **Evidence.** A restore from the off-machine repository to a scratch PostgreSQL instance, checked by the project's verifier: per-table row counts match, referential integrity holds, capture tables are continuous, and per-table content digests match.
- **Measured.** By performing the restore and running the verifier.
- **Current state.** Demonstrated: a full restore from the Backblaze repository was performed and verified on 19 August with all per-table digests identical, plus point-in-time recovery to an arbitrary timestamp. Additionally, on 3 to 4 September a 26 GB scratch backup set was restored from the repository and verified with zero digest mismatches for the attachment sizing exercise. Nightly backups run unattended; a full backup on Sundays and incrementals otherwise.

  **One observation to carry, report only.** For a 286 MB cluster the nightly backups took about 40 seconds through 3 September, then 16 minutes on 5 September, 6 hours on 6 September (the Sunday full), and 48 minutes on 7 September. The 4 September run aborted on a write-ahead-log archive timeout. The 6 September log shows a 17-minute initial checkpoint and then very sparse activity for hours with a handful of HTTP and socket retries against Backblaze. The cause is not established. Backups are completing and the repository reports status ok, but backup reliability is one of the tripwires named in the byte-store ruling, so this belongs on the watch list.
- **Old evidence.** Counts. Point 7 was untouched by the 3 September ruling.
- **Remains.** The restore repeated inside the final session, against the store as it stands then.
- **Natural or action.** Requires an action: Claude Code or a terminal performs the restore and verification. It cannot be done from the app.
- **In the final session.** Yes.

---

## 2. The separate fifty hand-labelled exchanges

This is a work-package acceptance criterion, not one of the seven closing points. The governing sentence, from WP-0.9's "Verified by" list:

> "Classifier accuracy: across fifty real exchanges hand-labelled by Lord Armand, hard exclusions are never classified consequential (zero tolerance — these are unambiguous), and disagreements on the inclusion test are reviewed and used to tune."

And the classification contract it refers to, from the partner-systems baseline §4.8: "an exchange is consequential for deliberation purposes when both hold: 1. A choice is being made among alternatives — stated explicitly or implied by the request. 2. The choice binds later work: creative direction, approach, priority, scope, or a standard for quality." with six hard exclusions "checked first": retrieval, lookup or search; a fact being stated, confirmed or corrected; execution of a task whose approach is already decided; status, progress, schedule or cost queries; logistics and scheduling; conversation containing no choice. And: "Where classification is genuinely borderline, the exchange is captured and marked uncertain."

**Settling the disagreement.** The claim "the fifty classifications require consequential turns" is **wrong**. The criterion says "fifty real exchanges", not fifty consequential ones, and half of what it tests, "hard exclusions are never classified consequential", can only be checked on exchanges that are *not* consequential. The fifty are ordinary exchanges of real use, whatever the classifier said about them.

- **Do all classified exchanges qualify, including ordinary verdicts?** Yes. Any real exchange on which the classifier delivered a verdict qualifies, including not-consequential verdicts.
- **Are both kinds required?** Effectively yes, though no ratio is stated. The zero-tolerance clause needs exchanges that fall under a hard exclusion; the inclusion-test clause needs exchanges where a choice binding later work is at stake. A set of fifty with neither kind could not exercise the criterion.
- **Do hard exclusions count?** Yes. They are the zero-tolerance half of the test.
- **Do failed or unestablished classifications count?** No. Ruled 3 September: "An unparseable classification attempt is not a classification and counts for nothing." Since that date the service records every turn's classification, established or not; only rows marked established carry a verdict to label against.
- **Do contaminated deliberations affect whether the classification counts?** No. Classification and ordering are separate records. Contamination concerns whether the blind position was independent; it says nothing about whether the classifier's verdict was right.
- **Is there a required balance or sampling rule?** None is stated. The exchanges are real ones from use; nothing is to be manufactured, per the resume ruling of 7 September.
- **What does "hand-labelled" mean?** Joseph reads the exchange and assigns his own verdict under the same contract: consequential, uncertain, or not consequential, and where not consequential, which hard exclusion applies if one does.
- **Who supplies the label?** Joseph. "Hand-labelled by Lord Armand."
- **What is agreement or disagreement?** Joseph's label compared with the recorded verdict and recorded hard exclusion for that exchange. A hard exclusion in his label against a recorded consequential verdict is the zero-tolerance failure. Any other difference is a disagreement on the inclusion test, "reviewed and used to tune."
- **Acceptance condition.** Two parts, no numeric accuracy threshold: zero cases where an exchange Joseph labels as a hard exclusion was classified consequential; and every inclusion-test disagreement reviewed, with the classifier tuned in response. Tuning is engineering.
- **Current valid count.** Zero labelled. Zero classifications exist in the live store since the restart, because no live turn has been sent since the repaired service was deployed on 7 September.

**The mechanics, stated plainly.** Since 3 September every turn writes a durable classification record: the verdict, the hard exclusion if any, whether a verdict was established, the attempt count, and the identities of the classifier calls. That record is readable through the service's conversation detail and through the database. **The desktop app does not display it, and there is no place anywhere in the system to record Joseph's label.** Hand-labelling is therefore NOT CURRENTLY USER-ACCESSIBLE. Before the fifty can accumulate, a decision is needed on where labels live and how the verdict is shown, and then engineering to build it. Until then the classifications are accumulating on the record, but the labels are not.

---

## 3. What Joseph personally does, step by step

Location tags: [VAL APP] the desktop application; [TERMINAL] a shell command; [FILE] a document; [CLAUDE CODE] an instruction to the implementation engineer; [AUTOMATIC] happens without action; [OTHER] outside all of these.

### A. Judged events

- **What can be judged.** Any reply Val has sent. Every Val message in a conversation carries the control, so a reply can be judged immediately or at any later time by scrolling back to it.
- **The button.** [VAL APP] Under the Val message, press **"Judge this"**.
- **The choices.** [VAL APP] A drop-down with four values: **accept**, **reject**, **request revision**, **correct**. A field labelled "what is being judged" for the subject. A field labelled "why — in your own words" for the reason. Then either **"Record"** or **"He declines to give a reason"**, or Cancel.
- **What a valid reason requires.** Words of Joseph's own. A rejection without a reason is not accepted silently: the service answers with the prompt for one, and the app shows it. Pressing "He declines to give a reason" records the event with reason source *absent*, never an invented reason. A reason given records reason source *stated*.
- **Later or immediately.** Either. The control is on every Val message permanently.
- **Where it is captured.** [VAL APP] Under the message, a line appears in the form "accepted — the subject · the reason (stated)" or "· no reason given (absent)". [AUTOMATIC] The row is durable the moment the line appears.
- **Current valid count.** 18 events: 14 accepted, 3 rejected, 1 revision requested, 0 corrected. All reasons stated. Twenty are needed for the hand-check sample, and one correction is needed for the one-of-each criterion.

### B. Classification hand-labelling

- **Where the classifier verdict is seen.** [VAL APP] Nowhere. The app does not display classifications. The verdict is on the record and visible only through developer inspection: [CLAUDE CODE] asking for the conversation's classification rows, or the service's conversation detail.
- **Is there a user-facing interface today?** No. NOT CURRENTLY USER-ACCESSIBLE.
- **What is clicked or typed to assign a label.** Nothing exists. There is no label field, table, or control. A label written into a chat message to Val would be conversation content, not a label.
- **Batch review after conversations, or turn-by-turn?** Undefined until the mechanism exists. The governing text does not require turn-by-turn; batch review of real exchanges after the fact is compatible with "fifty real exchanges hand-labelled."
- **How to know the label was saved.** Not applicable until a mechanism exists.
- **How to see progress toward fifty.** Not applicable until a mechanism exists. Classification rows themselves can be counted by [CLAUDE CODE].

What Joseph does now: continue real conversations, which accumulate classification records automatically. When ready, rule on the labelling mechanism so it can be built.

### C. Consequential deliberation, point 5

What has to happen in a conversation, described so it can occur naturally rather than be staged:

- **What makes an exchange consequential.** The classifier's contract, quoted in section 2: a choice among alternatives, stated or implied, and the choice binds later work — creative direction, approach, priority, scope, or a standard for quality. Both parts. Checked first are the six hard exclusions; if one applies the exchange is not consequential regardless of phrasing.
- **Is expressing a preference sufficient?** No. A preference with no choice at stake, or a choice that binds nothing afterwards, is not consequential. Conversely, a consequential exchange with no preference in it never reaches the blind step at all: the governing rule is "Where no preference is present, step 1 detects it and steps collapse to one call." So for point 5 evidence, both are needed in the same message: a real choice that binds later work, and a stated preference that can be separated from the question.
- **Hard exclusions.** Retrieval, lookup or search; a fact stated, confirmed or corrected; execution of a task whose approach is already decided; status, progress, schedule or cost; logistics and scheduling; no choice present.
- **What preference separation has to succeed.** The strip removes whole clauses expressing Joseph's preference, and since 7 September also any clause asserting or presupposing what Val previously believed and any framing that depends on it, such as "defend X or change your mind." The house rebuilds the blind question from the original text minus exactly those spans, verbatim. If a span is not found verbatim, if removing the spans would require rewriting the question, or if the preference is the question, separation is not established.
- **ordering = enforced.** The blind position was formed on the rebuilt question with nothing preference-bearing and no attributed prior in it, before Val saw the full message. The logged payload proves it.
- **ordering = contaminated.** Separation was not established, so the blind position was formed with the whole message in view, and the record says so. Valid evidence of the contaminated path; never evidence of enforcement.
- **Which rows count for point 5.** A blind-position row with ordering enforced, resolved by a deliberations row with an outcome, from a real live turn on or after 7 September.
- **Which do not.** Contaminated rows; blind rows with no deliberation outcome yet (position recorded, outcome pending); manual retroactive markings, which are recorded as contaminated by definition; anything in a scratch database; anything from the 3 to 7 September pause.
- **Do held, updated, and agreed from the start all qualify when enforced?** Yes. All three are outcomes of an enforced deliberation. The work-package criterion additionally wants all four outcome values seen in real use; the fourth, overridden, is Joseph's manual record of overriding her, never her own report.
- **How to see afterward that it was recorded.** [VAL APP] Under the user message that started it, a block appears: "consequential", "Her position:", her confidence, her reasoning, the ordering label — "formed blind, before exposure to the stated preference" or "contaminated — the preference could not be separated; this position was NOT independently formed" — the withheld preference text, and the outcome once it exists: "she held", "she updated", "agreed from the start", or "outcome pending" while no row exists. [CLAUDE CODE] The logged blind payload and the withheld line are in the service log and are read on request.

Where the preference is stated in a way the strip cannot separate, the record will honestly say contaminated. That is not a failure of use; it is the mechanism declining to claim what it cannot prove.

---

## 4. The final single-session demonstration

**The scope of the session, settled.** The governing sentence requires the seven properties to "hold simultaneously, demonstrated in one session." The long-running counts are work-package acceptance criteria — twenty hand-checked events, one of each judgment type, the fifty hand-labelled exchanges, all four outcome values in real use, the day of real work through the app, the dashboard comparison — and the definition of done requires them to be met. **They must already be satisfied before the session closes the gate; they do not have to be accumulated inside the session.** The session demonstrates the seven properties together on a real conversation; it does not restart the counts.

**Preconditions, all complete before starting.**

1. A real project exists to attribute the session to. Today none does; creating one is NOT CURRENTLY USER-ACCESSIBLE and needs a decision plus a developer insert or a ruling to build project creation.
2. Twenty or more real judged events exist including at least one correction, and the twenty-event hand-check has been done and recorded.
3. Fifty real exchanges have been hand-labelled with zero hard-exclusion exchanges classified consequential and every inclusion disagreement reviewed. Requires the labelling mechanism to be ruled and built first.
4. All four deliberation outcomes have been seen in real use, including at least one manual override.
5. A full day of real work has been done entirely through the app.
6. The dashboard-versus-table comparison has been done for a day of real use.
7. Claude Code is available during the session for the restart, the restore, and log inspection.

**The session.**

- **Step 1.** [VAL APP] Start a new conversation, selecting the real project. *Result:* the conversation appears attributed to it. *Evidence:* the conversation row carries the project. *Claude Code:* not needed.
- **Step 2.** [VAL APP] Make an ambiguous project reference where two names could match, if two projects exist. *Result:* Val asks which, rather than guessing. *Evidence:* the clarification response; no turn is recorded until answered. *Claude Code:* not needed. If only one project exists, this cannot be shown and the point relies on the August demonstration.
- **Step 3.** [VAL APP] Conduct real work: several ordinary turns. *Result:* replies arrive. *Evidence:* messages, classification rows, model-call rows. *Claude Code:* not needed.
- **Step 4.** [VAL APP] Judge at least one reply with "Judge this", giving a reason. *Result:* the event line appears under the reply. *Evidence:* an execution-events row with reason source stated. *Claude Code:* not needed.
- **Step 5.** [VAL APP] In the natural course of the work, put a real choice that binds later work to Val together with your preference, separable from the question. *Result:* the consequential block appears under your message with "formed blind, before exposure to the stated preference" and an outcome. *Evidence:* an enforced blind-position row and a deliberations row. *Claude Code:* needed to read the logged blind payload and the withheld line, which is the "demonstrable from the logged blind-call payload" half of point 5. If the record says contaminated, point 5 is not shown by that exchange.
- **Step 6.** [TERMINAL] or [CLAUDE CODE] Stop the desktop service and PostgreSQL, then start both. *Result:* the app reconnects; the conversation reopens with every message present. *Evidence:* the same conversation continues, sequence unbroken. *Claude Code:* needed, or a terminal.
- **Step 7.** [VAL APP] Continue the conversation with at least one more turn after the restart. *Result:* a reply. *Evidence:* messages after the restart in the same conversation. *Claude Code:* not needed.
- **Step 8.** [CLAUDE CODE] Ask for the model-calls check for the session: every call has a row, cost, project, task type, and the accounting view shows zero uncosted calls. *Evidence:* the query result. *Claude Code:* needed.
- **Step 9.** [CLAUDE CODE] Ask for a restore of the current backup from Backblaze to a scratch instance and the verifier's report. *Result:* row counts match per table, referential integrity holds, capture tables continuous, per-table digests identical. *Evidence:* the verifier's output, recorded in the evidence index. *Claude Code:* needed. Allow hours if the recent backup slowness persists.
- **Step 10.** [CLAUDE CODE] Ask for the session's evidence to be written into the evidence index as the gate demonstration, then rule the gate closed. *Evidence:* the recorded session and the ruling.

---

## 5. What accumulates naturally versus what requires Joseph

**A. Accumulates through normal use.**

| Item | Progress |
|---|---|
| Real conversation through the app (point 1) | 1 live conversation, 44 messages |
| Classification records on every turn | 0 since the restart; every turn from now on writes one |
| Consequential deliberations, enforced (point 5) | 0; needs real exchanges with a choice, a binding consequence, and a separable preference |
| Model-call rows with cost (point 6) | 88 all time; zero uncosted this month |
| Judged events (point 4) | 18, whenever a reply deserves judging |
| Nightly backups (point 7) | running; durations abnormal since 5 September, cause not established |
| Consequential-turn latency observation | none yet; expected 15 to 22 seconds |

**B. Requires a deliberate action or review pass.**

| Item | Progress | Who |
|---|---|---|
| A real project to work in | none live; the app cannot create one | decision by Joseph, then engineering |
| One `corrected` judgment in real use | 0 of 1 | Joseph, in the app |
| Twenty-event hand-check of reason source | not done; 18 events exist | Joseph reads, Claude Code records |
| Fifty hand-labelled exchanges | 0; no mechanism exists | ruling by Joseph, then engineering, then Joseph labels |
| All four outcomes in real use, including one manual override | 0 of 4 | Joseph, in the app; override via "Mark consequential" |
| A full day of real work through the app | not recorded | Joseph's statement |
| Dashboard-versus-table comparison for a day | not done | Joseph reads the console, Claude Code produces the table figure |
| Restart and restore in the final session | pending | Claude Code |
| Classifier tuning from inclusion disagreements | none yet | engineering, after labels exist |

Engineering or Claude Code rather than Joseph: project creation; the labelling mechanism; classifier tuning; the restore and restart in the session; recording the evidence index.

---

## 6. The separate Layer 0 gate list

A different document from the seven closing points. Its standing rule, quoted: "review happens at the Layer 0 gate, not continuously. A finding that is not tied to a stated acceptance criterion goes here, not into a corrective round. Items here are neither defects against accepted criteria nor decisions needed now."

**Correction:** "seven open items" is accurate as a count of entries and misleading as a description. None of the seven is a Layer 0 closure blocker. They are review items to be looked at when the gate is reached, and one already carries Joseph's recorded inclination to reject it.

1. **A set-once transmission marker on budget reservations**, so restart reconciliation could release holds proven never sent instead of expiring them conservatively. Status: open review item. Joseph's recorded objection, 19 August: the marker records the boundary being entered, not transmission occurring, so it does not resolve the indeterminacy; current inclination is to reject. Needs: a decision at the gate, probably rejection. Not a blocker.
2. **Error-kind granularity on failed calls is not durable** beyond the recorded terminal state "failed". Status: open review item. Needs: a decision on whether to record the kind. Not a blocker.
3. **Lexical retrieval limit**: a question sharing no vocabulary with earlier conversation will not recall it; semantic retrieval needs four recorded decisions listed in the open-decisions document, where it is marked deferred and not a decision required now. Status: open, deferred. Needs: nothing now. Not a blocker.
4. **A provider inventing a new stop reason lands in the unknown state and fails closed** until an adapter mapping is added. Status: open by design; the behaviour is the intended fail-closed. Needs: nothing unless it occurs. Not a blocker.
5. **Non-conversation callers must branch on truncated and filtered terminal states.** Status: the classification, strip, and blind-position callers now do so (a truncated classifier reply is treated as no verdict; a truncated blind reply is no position). Review item to confirm at the gate. Not a blocker.
6. **The history window of forty turns has never been exercised by a real conversation longer than forty turns.** Status: open; the live conversation has 44 messages, which is 22 turns. Needs: nothing but use; a review at the gate. Not a blocker.
7. **Audit for other naive-timestamp boundaries** of the shape fixed on 31 August, where a computed timestamp is reinterpreted in the session time zone. Status: open; the audit has not been performed. Needs: engineering, at the gate. Not a blocker, though it is the one item that is real work.

---

## 7. Tracks and parallel work

**Track A — the Layer 0 gate.** Purpose: accumulate the evidence in sections 1 to 5 through real use and close the gate. Authorized: yes, mandatory. Designed and implemented: the mechanisms are implemented and each has been demonstrated at least once; the evidence is accumulating from real use. Usable today: yes, it is the app as it stands. Blocked: no. Development before the gate closes: this is the gate.

**Track B — Layer 1 presence.** Purpose: speech-to-text input, ElevenLabs voice output, avatar state loops, lip-sync. Authorized: yes, in parallel, under a hard constraint quoted from the ruling: "it consumes the existing conversation contract and changes nothing about it (no new table, no new column, no migration, no change to what the conversation endpoints return); a presence feature needing any of those stops and waits for the gate." Also: the avatar never depicts a state the system cannot confirm. Designed: no. Implemented: no; nothing exists in the code. Demonstrated: no. Usable today: no. Blocked: no; it awaits Joseph saying begin, which he has not yet said. Development before the gate: permitted.

**Track C — attachment substrate and image vision.** Purpose: let Joseph attach an image to a conversation and have Val see it, on a substrate designed once for all future modalities. Authorized: yes, opened 2 September, "nothing else." Designed: yes, Attachment Substrate contract version 1.2 is accepted and governing, and on 7 September the byte store was ruled: image bytes stay in PostgreSQL. Implemented: **no; zero implementation exists.** No attachment tables, no upload path, no vision call. Demonstrated: no. Usable today: no. Blocked for development: no; the contract's pre-implementation deliverable is discharged and implementation may proceed. Blocked for live use: yes, by WP-0.11, below. Development before the gate: permitted, on the existing path.

**WP-0.11 — budget-control hardening, in plain terms.** Today the system has one number, a $200 monthly ceiling written into the code, and when a call would exceed it the routing quietly steps down to a cheaper model before refusing. The ruling of 2 September found that wrong on two counts: the planning figure is not a safety ceiling, and silently doing worse work to stay under a number contradicts the quality priority. WP-0.11 replaces this with: an operating target that only reports and never refuses; a separate runaway safety ceiling, at a value Joseph sets, that is the only thing that can refuse a call; a clear warning before the ceiling is reached; the ability for Joseph to raise the ceiling at runtime without editing code, changing schema, or restarting, with the raise recorded with amount, scope, time, and actor; and the removal of the silent step-down, so a ceiling hit refuses honestly. Status: recorded, not begun.

What WP-0.11 blocks, quoted: it "does not block the attachment migration or the internal vision implementation after the storage ruling; those proceed on their existing path. It does block Track C becoming an operational working-day capability, and it blocks visual conversations contributing evidence to the Layer 0 gate." "Not a development blocker. A live-use blocker."

The current questions, settled:

- **Can attachment and image development proceed now?** Yes. The contract is governing, the byte store is ruled, and WP-0.11 does not block development.
- **Can image vision be used for real working-day conversations now?** No. Nothing is implemented, and even once it is, live working-day use waits for WP-0.11.
- **Are document attachments authorized?** No. Track C is images only: "Attachment Substrate v1 and attachment-scoped image vision, nothing else." Documents sit in the post-gate order as a sibling of image vision, to begin after the gate closes.
- **Are document attachments implemented?** No. Nothing exists.
- **What must happen before documents become available?** The Layer 0 gate closes; then message revision and retraction, first in the post-gate order; then a ruling to begin document comprehension as a sibling consumer of the substrate, including how document-derived views such as page text and figures are represented under the contract's provenance rules; then implementation; and WP-0.11 before live use if it is not done by then.

---

## 8. Built today versus ruled but not built

**A. Exists and runs today.**

- Text conversation through the desktop app, with the persona loaded whole into every call.
- Persistence and history: every message durable in PostgreSQL; conversations resume across restarts; project-scoped recall of earlier conversations.
- Classification of every turn, schema-constrained, with a durable per-turn record since 7 September; an unclassifiable turn ends unanswered rather than proceeding as ordinary.
- Preference stripping with mechanically derived remainder, occurrence locators, and attributed-prior removal; separation failures recorded as contaminated.
- Blind positions: formed on the stripped question with the persona and no history, recorded durably before the response call, payload logged.
- Deliberation outcomes: held, updated, agreed from the start from Val's own checked verdict; overridden by manual record only; inconsistent verdicts recorded as no outcome.
- Judgment capture: accept, reject, request revision, correct, with reason and reason source, from the app.
- Cost capture: a costed row for every provider call, reservations before the call, a $200 ceiling with the silent step-down still present until WP-0.11.
- Execution events: same as judgment capture.
- Backups and restore: nightly encrypted backups to Backblaze with a Sunday full; restore verified from the off-machine repository on 19 August and at volume on 3 to 4 September.
- Manual consequential marking from the app.

**B. Authorized or governed but not implemented.**

- Attachment substrate: contract version 1.2 governing, byte store ruled, **zero implementation**.
- Image upload: authorized under Track C, not implemented.
- Image vision: authorized under Track C as attachment-scoped sight, not implemented; live use additionally waits for WP-0.11.
- WP-0.11 budget-control hardening: ruled, minimum shape recorded, not begun.
- Track B presence — voice output, speech input, avatar, lip-sync: permitted in parallel under the no-schema constraint, not begun.
- Hand-labelling mechanism for the fifty: required by the criterion, no mechanism ruled or built.
- Project creation from the app: not present; the app only selects existing projects.

**C. Not yet authorized or deliberately held.**

- Document upload and reading: behind the gate; a post-gate sibling of image vision.
- Message revision and retraction: requirement recorded, first in the post-gate order; today a sent message is permanent.
- Audio and video: behind the gate, "each designed against specific real tasks, with a cost model established before implementation."
- MCP and tools of any kind: Layer 2; no tool is exposed to any model call today, and the only MCP component in the repository is an empty placeholder. No arbitrary code execution tool is ever exposed, permanently.
- Local inference: Layer 1; until it exists the strip runs on the cheapest cloud route under a recorded, tripwired deviation.
- Per-content data classification and per-call eligibility checks: Layer 2; Layer 0 satisfies eligibility structurally because every configured route is eligible for Protected content.

---

## 9. Corrections to statements already in the chat

- **"The fifty classifications require consequential turns."** Wrong. The criterion is fifty real exchanges hand-labelled, of any kind; half of the test can only be met on exchanges that are not consequential. See section 2.
- **"Expressing a preference and asking Val what she thinks is enough by itself to make a turn consequential."** Wrong. The contract needs a choice among alternatives and a choice that binds later work, with the hard exclusions checked first. A preference alone is neither. Separately, a consequential exchange with no preference never reaches the blind step. See section 3C.
- **"The twenty judged events are almost all still outstanding."** Wrong. Eighteen real judged events exist, all with stated reasons. What is outstanding is two more events at minimum, one correction, and the hand-check itself.
- **"Images are ready except for a user decision."** Wrong. The contract and the byte-store decision are done; the implementation is zero. Development may proceed; live use additionally waits for WP-0.11, which is also not begun.
- **"Documents are blocked by engineering rather than scope."** Wrong. Documents are blocked by scope: Track C is images only and documents are behind the gate in the post-gate order. There is no document engineering to be blocked yet.
- **"The seven-item gate list and the seven closing points are the same thing."** Wrong. The closing points are the definition of Layer 0 completion. The gate list is a set of review items explicitly "neither defects against accepted criteria nor decisions needed now," none of which blocks closure.

---

## WHAT JOSEPH DOES NEXT

1. **Decide the first real project's name** and have Claude Code create it, or rule that the app should be able to create projects. Nothing in the final session can be attributed until a live project exists.
2. **Work with Val normally in the app, inside that project.** Every turn now writes a classification record. Consequential deliberations will come from the work itself: when a real choice that shapes later work is put to her together with your view of it, stated so it can be separated from the question. Do not stage it.
3. **Judge replies as they deserve it**, with "Judge this" and a reason in your own words. Judge a correction when one genuinely occurs. Reach twenty.
4. **When a deliberation is recorded, look at the block under your message.** "Formed blind" counts toward point 5; "contaminated" does not, and is not a failure of use. Note whether the turn took longer than about 22 seconds.
5. **Rule on the hand-labelling mechanism**: where your label is recorded and how the verdict is shown to you. Until then the fifty cannot start, however many classifications accumulate.
6. **Say begin on Track B, or not.** It is permitted and untouched.
7. **Let attachment substrate implementation proceed** when you want it; it does not need a further ruling. Image vision in live work waits for WP-0.11, which is its own package and needs your ceiling number when it begins.
8. **When twenty judged events exist, do the hand-check** by reading them in the app, and have Claude Code record it. When a full day has gone by entirely through the app, say so. Then do the dashboard comparison for one day with Claude Code producing the table figure.
9. **Watch one operational item**: nightly backups have been taking far longer than before since 5 September for no established reason. Ask for the cause to be established if it persists.
10. **When every precondition in section 4 is met, run the session** in section 4's order with Claude Code present, then rule the gate closed.
