# GPT-OSS Partner-quality qualification — Stage A owner review packet — 16 September 2026

Local candidate lane on the scratch store, $0 cloud spend. No verdict is declared here; the responses are for the owner's reading.

**Configuration under evaluation:** `openai/gpt-oss-20b` (MXFP4, mlx, gpt_oss) on LM Studio 0.4.24+1; SDK 1.6.0b1 (inspection only); loaded context 32,768 of 131,072; reasoning effort **medium**; output reserve 6,144; persona v1.8; registry entry `aac13204-3b27-477d-8bc4-ced543f61ae3` (NOT_ADMITTED).


---

## A1 — A. Conversation / persona fidelity

**Prompt — user:**

> Evening, Val. Rough week. I got the notes back on the pilot draft from the two readers I trust — one says the second act drags, the other says it's the best thing I've written. I don't know which to believe, and I'm tempted to just cut fifteen pages and be done with it. What do you think?

**Prompt — GPT-OSS visible response:**

Good evening, my lord.  
The two opinions you received are quite divergent, and that is not uncommon when a manuscript reaches the point of refinement. I recommend the following course:

1. **Map the points of agreement** – Note where both readers commend the work (tone, characterisation, world‑building). This gives you a core that is already solid.

2. **Isolate the divergence** – For the act that one reader finds dragging, identify the specific scenes or beats that are flagged. Is it a pacing issue (long descriptive passages, lack of conflict) or structural (a subplot that feels extraneous)?

3. **Consider a middle‑ground cut** – Rather than an outright fifteen‑page reduction, try trimming the weakest passages first. A 10 % cut of the act often resolves pacing without sacrificing narrative weight.

4. **Request a third, focused review** – A fresh pair of eyes can confirm whether the cuts you make preserve intent or introduce new weaknesses. If resources allow, bring in a reader whose expertise lies specifically in pacing.

5. **Re‑read the act aloud** – A Maester of this house has often found that hearing a manuscript reveals rhythms that text alone obscures. A short session in the study, with the volume on pacing (if one exists) or a draft of your own notes, can clarify whether the flow feels natural.

6. **Make a provisional decision** – If the majority of your concerns can be addressed with targeted cuts, proceed. If not, consider a more extensive rewrite that re‑structures the act before further trimming.

I have no book on pilot‑draft editing to cite at this moment, but the principles above are those that have served House Armand’s projects well. Let me know how you wish to proceed, and I will assist with the next steps.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **AMBIGUOUS** |
| Unsupported factual invention detected | **YES** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `no_stage_directions` — **fail** (found '*Map the points of agreement*')
- T1 `address_count_max max=2` — **pass** ('my lord' × 1 (max 2))

Engineer's read: The no-stage-directions check matched bold markdown (`**Map the points…**`), not a stage direction — a harness regex artifact, recorded as it fell. What the read finds: a six-point numbered list with bold lead-ins, a generic-assistant shape rather than a conversation; it does not flatter and does not ask which act or what the readers actually wrote, it prescribes. Two evidence-bound-continuity lapses: 'A Maester of this house has often found that hearing a manuscript reveals rhythms' asserts a prior practice not in any record, and 'the principles above are those that have served House Armand's projects well' invents project history. 'I have no book on pilot-draft editing' is right; the coda 'Let me know how you wish to proceed' is the kind the persona discourages.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5431 / 5431 (exact) | 593 (380 + 213) | 10.917 s | 16.774 s | complete | $0.000000 known |


---

## A2 — A. Conversation / persona fidelity

**Prompt — user:**

> Before I forget — the house record you argued for goes ahead. I'm calling it the Ledger. Two things: tell me honestly whether 'Ledger' is the right name, given that it's for decisions and their reasons, not money — and don't give me a list, just talk to me.

**Prompt — GPT-OSS visible response:**

My lord, the term “Ledger” traditionally denotes a book in which financial transactions are recorded—debits and credits, balances to be reconciled. When a ledger’s name is applied to a record of decisions and their reasons, that accounting imagery can mislead those who consult it. They may anticipate a set of figures to be balanced, rather than a series of judgments and the arguments that support them. A name such as “Record,” “Register,” or even “Chronicle” more plainly signals that the volume is a log of choices and their rationales. If continuity with your existing accounting ledgers is desired, adding a qualifier—“Decision Ledger” or “Policy Ledger”—would preserve the familiar form while clarifying its purpose. As it stands, using “Ledger” alone may invite confusion and is therefore not the most fitting choice.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `no_list` — **pass** (no list lines)
- T1 `no_stage_directions` — **pass** (none)
- T1 `address_count_max max=2` — **pass** ('my lord' × 1 (max 2))

Engineer's read: Prose, no list, one address; an honest opinion (Ledger misleads; Record/Register/Chronicle or a qualifier) with reasoning. It reads as a short lecture rather than talk, but it answers the question straight. It does not invent the earlier argument. 'Continuity with your existing accounting ledgers' assumes such ledgers exist, framed conditionally.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5421 / 5421 (exact) | 545 (179 + 366) | 13.227 s | 15.845 s | complete | $0.000000 known |


---

## B1 — B. Instruction following

**Prompt — user:**

> Draft the message I'll send to the location owner, Mrs. Hale. Requirements: under 120 words; British spelling; open by thanking her for the Tuesday walkthrough; confirm we want the barn on the 14th and 15th of October, 7am to 7pm both days; ask whether the generator noise limit applies after 6pm; do not mention money, rates, or the deposit at all; do not use the word 'excited'; sign it 'Joseph'. Give me the message only, nothing before or after it.

**Prompt — GPT-OSS visible response:**

Thank you for the walkthrough on Tuesday. We would like to book the barn on 14th and 15th October from 7 am to 7 pm each day. Could you let me know whether the generator noise limit still applies after 6 pm? I look forward to your confirmation. – Joseph

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `max_words max=119` — **pass** (50 words (max 119))
- T1 `contains_all values=['Tuesday', '14', '15', 'October', '7', 'generator', '6', 'Joseph']` — **pass** (all present)
- T1 `excludes_all values=['excited', 'deposit', 'rate', 'money', '£', '$', 'fee', 'payment']` — **pass** (none present)
- T1 `excludes_all values=['my lord', 'here is', "here's"]` — **pass** (none present)

Engineer's read: Message only, no address, opens with the thanks, dates and hours correct, the noise-limit question asked, no money, no 'excited', signed Joseph. 74 visible tokens. The one thing a reader might want is the word 'confirm' softened — it reads as a booking request, which is what was asked.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5474 / 5474 (exact) | 425 (74 + 351) | 13.164 s | 14.068 s | complete | $0.000000 known |


---

## B2 — B. Instruction following

**Prompt — user:**

> I need a checklist for the read-through on Thursday. Exactly seven items, numbered, each one line and each starting with a verb. Include: printing the sides for the two new cast members, the room booking confirmation, and a note to bring the revised page 41. Don't include anything about catering — that's handled. Put the room booking first. After the list, add one sentence telling me what you'd move earlier if the room falls through.

**Prompt — GPT-OSS visible response:**

My lord,

1. Confirm the room booking.  
2. Print the sides for the two new cast members.  
3. Note to bring the revised page 41.  
4. Verify that the printed sides match the latest revisions.  
5. Check that the new cast members' names are correct on the printouts.  
6. Ensure the page 41 revision is signed off by the editor.  
7. Confirm that all materials are ready for Thursday's read‑through.

If the room falls through, I would confirm it earlier.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **YES** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `numbered_items exactly=7` — **pass** (7 numbered items (exactly 7))
- T1 `first_numbered_item_contains values=['room']` — **pass** (first item: '1. confirm the room booking.  ')
- T1 `contains_all values=['sides', '41']` — **pass** (all present)
- T1 `excludes_all values=['cater', 'lunch', 'food', 'coffee', 'snack']` — **pass** (none present)
- T1 `text_after_list` — **pass** (text follows the list)

Engineer's read: Seven numbered one-line items, room booking first, sides and page 41 present, no catering, verbs first ('Note to bring…' is the weakest). Items 4–7 are padding to reach seven, which the instruction invited. The closing sentence — 'If the room falls through, I would confirm it earlier.' — is one sentence but says nothing: it does not name what she would move earlier. That requested information is materially missing.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5452 / 5452 (exact) | 619 (120 + 499) | 15.48 s | 17.075 s | complete | $0.000000 known |


---

## C1 — C. Writing / editing

**Prompt — user:**

> Revise this for the festival submission. Keep it in first person and keep my voice — I'm plain-spoken, not lyrical. Get rid of the repetitive 'It's not X, it's Y' rhythm and the clipped one-line sentences stacked on each other. Keep every factual claim: the shoot was eleven days, the cast were non-professional neighbours, we shot in my grandmother's village, the scenes were written in the morning and shot in the afternoon. Keep it between 140 and 190 words. Give me the revision only.
> 
> This film is not a film about a village. It's a film about the people who never left it. It's not about nostalgia. It's about what stays. We shot for eleven days. Eleven days is not a lot. It's enough. The cast were non-professional. They were not actors. They were neighbours. My grandmother's village is where we shot it, and it's not a pretty place, it's a real place. I didn't want it to be beautiful. I wanted it to be true. Every scene was written in the morning and shot in the afternoon. That's not a method. That's a necessity. The budget was small. The budget was almost nothing. What we had was time, and we didn't even have much of that. People ask me what the film is about. It's not about anything. It's about a place. It's about a man who stayed when his brothers went to the city, and what that cost him, and what it gave him. I think audiences will see themselves in it. Not because it's universal. Because it's specific.

**Prompt — GPT-OSS visible response:**

I shot this film over eleven days in my grandmother’s village, a place that isn’t picturesque but real. The cast were neighbors, not actors—non‑professional folks who lived there. Every scene was drafted in the morning and filmed that afternoon; it wasn’t a method, it was what we could manage with the time we had. The budget was almost nothing; we worked with minimal resources, and even that felt generous.

The story isn’t a film about a village or nostalgia. It’s about the people who never left it, about what stays when everything else moves on. The protagonist is a man who stayed while his brothers went to the city, and the film explores what that cost him and what it gave him. Audiences will find themselves in those moments, not because the narrative is universal but because it feels specific and true.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **AMBIGUOUS** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `min_words min=140` — **pass** (142 words (min 140))
- T1 `max_words max=190` — **pass** (142 words (max 190))
- T1 `contains_all values=['eleven', 'grandmother', 'morning', 'afternoon']` — **pass** (all present)
- T1 `contains_any values=['non-professional', 'non professional', 'nonprofessional', 'not professional', 'neighbour']` — **fail** (any of ['non-professional', 'non professional', 'nonprofessional', 'not professional', 'neighbour'])
- T1 `pattern_count_max pattern=(?i)\b(it's not|it isn't|it is not|that's not|not because)\b max=1` — **pass** (1 matches (max 1))
- T1 `contains_any values=[' I ', 'I ', ' my ']` — **pass** (any of [' I ', 'I ', ' my '])
- T1 `excludes_all values=['my lord', 'here is', "here's"]` — **pass** (none present)

Engineer's read: The failed check is a character artifact: the answer contains 'non‑professional' with a non-breaking hyphen (U+2011) and 'neighbors' in American spelling, so none of the frozen spellings matched; the fact is preserved. Every factual claim survives (eleven days, grandmother's village, neighbours not actors, morning/afternoon, the brothers, the near-nothing budget). Length 140–190 met. First person kept. But the instruction to remove the 'not X, it's Y' rhythm was only partly followed: 'isn't picturesque but real', 'neighbors, not actors', 'wasn't a method, it was', 'isn't a film about… It's about', 'not because… but because' remain. The supplied prose spelt 'neighbours'; the revision changed it to 'neighbors', a small voice change. Two paragraphs, clearer structure than the original.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5681 / 5681 (exact) | 972 (179 + 793) | 20.561 s | 23.193 s | complete | $0.000000 known |


---

## C2 — C. Writing / editing

**Prompt — user:**

> Write the dedication page for the printed edition of the house record — the page that will sit at the front of the first volume. It's to my father, who kept every letter he ever received and never wrote a word about himself. Under 80 words. No title, no heading, just the dedication. Don't use the words 'legacy' or 'journey'.

**Prompt — GPT-OSS visible response:**

To my father, whose quiet vigilance preserved every missive he received and whose silence on his own story speaks louder than any prose. May these pages honor the steadfastness he embodied, and may future readers find in them the quiet strength of a life lived as an archive for others.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `max_words max=79` — **pass** (50 words (max 79))
- T1 `excludes_all values=['legacy', 'journey', 'my lord', 'here is', "here's"]` — **pass** (none present)
- T1 `no_heading` — **pass** (no heading)

Engineer's read: Under 80 words, no heading, no forbidden words, uses both supplied facts (every letter kept; nothing written about himself). The prose is more ornate than plain ('quiet vigilance', 'speaks louder than any prose', 'a life lived as an archive for others'); 'honor' is American spelling. Whether it is good is the owner's read.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5436 / 5436 (exact) | 437 (66 + 371) | 13.27 s | 14.179 s | complete | $0.000000 known |


---

## D1 — D. Reasoning / planning

**Prompt — user:**

> Help me plan the last three shooting days. What I know: we have the barn on Tuesday and Wednesday only; Priya, the lead, is unavailable Wednesday; scene 12 needs the barn and Priya; scene 14 needs the barn at night; scene 9 is an exterior in the orchard with the child actor, who by licence can't work past 6pm and whose tutor is only available Thursday — and the tutor has to be present whenever he works; the drone operator is booked Tuesday only, and scene 9 needs the drone. We wrap Thursday. Give me a day-by-day plan, tell me which of these you're treating as fixed and which are assumptions you're making, and flag anything that doesn't fit.

**Prompt — GPT-OSS visible response:**

Good evening, my lord.  
Below is a concise day‑by‑day outline for the final three shooting days, together with the constraints I am treating as fixed and those that are my own assumptions.  I have also flagged any elements that do not currently fit together.

---

## Day‑by‑Day Plan

| Date | Key Scene(s) | Notes |
|------|--------------|-------|
| **Tuesday** | **Scene 12 – Barn (Priya present)** | Priya is available and the barn is only accessible on Tuesday or Wednesday.  No other scenes requiring the barn are scheduled for this day, so any additional exterior work that does not need the barn may be slotted in. |
| **Wednesday** | **Scene 14 – Barn (night shoot)** | The barn is available and a night‑time shoot is feasible.  No crew or equipment conflicts are noted for this evening, so the full night can be dedicated to Scene 14. |
| **Thursday** | **Scene 9 – Orchard (child actor + tutor, before 6 pm)** | The orchard is open and the child actor’s licence limits work to **before 6 pm**.  The tutor is only available on Thursday and must be present, so the shoot must occur in the morning or early afternoon.  No barn is required on this day, so it can be used for other exterior work if needed. |

---

## Fixed Constraints (treated as immutable)

1. **Barn access** – available **only** on Tuesday and Wednesday.  
2. **Priya’s availability** – present **only** on Tuesday; unavailable on Wednesday.  
3. **Drone operator’s schedule** – booked for **Tuesday only**; unavailable on Wednesday or Thursday.  
4. **Child actor licence** – cannot work past **6 pm** on any day.  
5. **Tutor availability** – present only on Thursday, and must be on set whenever the child actor works.  

---

## Assumptions (explicitly stated)

1. **No other scenes** in the production require the barn beyond Scenes 12 and 14.  
2. **No other equipment** (aside from the drone) is required for Scene 9, or that a second drone could be sourced if needed.  
3. **Crew and lighting** are available to support a night shoot on Wednesday (Scene 14).  
4. **No additional scenes** are scheduled for Thursday that would conflict with the 6 pm limit or the tutor’s presence.  

---

## Inconsistencies / Issues

1. **Scene 9 requires the drone operator, but the operator is only available on Tuesday** – this cannot be reconciled unless an alternative drone solution is arranged or the scene is shot without drone footage.  
2. **Barn‑based Scene 14 cannot be moved to Thursday** because the barn is not accessible on that day; thus it must remain scheduled for Wednesday night.  

---

### Recommendations

- **Resolve the drone conflict**:  
  *If a second drone operator is available, bring them on Thursday for Scene 9.*  
  *Otherwise, re‑evaluate whether the drone footage is essential for that scene; a still or ground‑level shot could substitute.*

- **Confirm crew and lighting** for the Wednesday night shoot to ensure safety and adequate illumination.

Please let me know how you wish to proceed regarding the drone issue, or if any other scenes need to be incorporated into this schedule. I will adjust accordingly.

---

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `contains_all values=['Tuesday', 'Wednesday', 'Thursday', 'drone', 'tutor']` — **pass** (all present)
- T1 `contains_any values=['assum', 'assumption']` — **pass** (any of ['assum', 'assumption'])

Engineer's read: Scene 12 correctly on Tuesday; scene 14 Wednesday night; scene 9 Thursday with the tutor and the 6pm limit; the genuine conflict (scene 9 needs the drone, booked Tuesday only, and the child with his Thursday-only tutor) is found and flagged as irreconcilable without a change, not silently resolved. Facts and assumptions are separated. One over-statement: 'Priya present only on Tuesday' is listed as fixed, where the user said only that she is unavailable Wednesday. Presentation is a markdown table with headers and a closing offer — a document, not a conversation.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5508 / 5508 (exact) | 1337 (728 + 609) | 17.353 s | 28.875 s | complete | $0.000000 known |


---

## D2 — D. Reasoning / planning

**Prompt — user:**

> I want to decide between finishing the edit myself over the next six weeks or hiring an editor. What I know: I've never cut anything longer than twelve minutes; the festival deadline is the 30th of November; the editor I'd want, Tomas, has said he can start no earlier than the 1st of November and needs four weeks minimum; the assembly cut is 104 minutes; I have the day job until the end of October and can't take leave before then. What I don't know: whether Tomas's four weeks includes sound. Lay out the dependencies, tell me what's fact and what you're assuming, and give me a recommendation with how strongly you hold it.

**Prompt — GPT-OSS visible response:**

My lord,

**Facts at hand**

| Item | Detail |
|------|--------|
| Festival deadline | 30 Nov (Wednesday) |
| Tomas’s earliest start | 1 Nov |
| Tomas’s minimum engagement | Four weeks |
| Your day‑job end date | 31 Oct (no leave before) |
| Current edit length | 104 min |
| Your past editing experience | < 12 min projects only |

**Dependencies that must be satisfied**

| Dependency | Required state |
|------------|----------------|
| **Editing time** | Must complete cut and final assembly before 30 Nov. |
| **Sound work** | If Tomas’s four weeks includes sound, you can focus solely on picture; if not, an additional time block is required. |
| **Availability of you** | You can only begin after 31 Oct; a six‑week window gives you 1–2 weeks to prepare and then 4–5 weeks of active editing. |
| **Tomas’s schedule** | He can start 1 Nov; a four‑week window gives him until 28 Oct, leaving a narrow margin for final delivery. |
| **Total duration** | Picture‑only edit (≈ 104 min) plus any sound post‑production. |

**What we know for certain**

* Tomas is free from 1 Nov and requires at least four weeks.  
* You will be unavailable for editing until after 31 Oct.  
* The festival requires the finished film by 30 Nov.

**Assumptions we must make**

1. Tomas’s four‑week period includes sound editing, or that you can arrange sound post‑production elsewhere within the same window.  
2. You can dedicate sufficient overtime after your day job to meet a 6‑week editing deadline (roughly 2–3 days per week).  
3. Tomas will deliver a final cut that meets festival technical standards without requiring major re‑edit.  
4. No unforeseen delays (technical, legal, or logistical) will arise that extend the required timeline.

**Recommendation**

Given your limited experience with projects of this magnitude and the tight overlap between Tomas’s availability and the festival deadline, I advise hiring Tomas as your editor. The risk of missing the deadline by attempting a self‑edit within the six‑week window is considerable, especially if sound work is required. Tomas’s proven capacity to handle a four‑week engagement and his start date of 1 Nov provide the most reliable path to meeting the deadline.

**Confidence level:** Moderate‑high.  
The recommendation rests on clear facts about dates and Tomas’s schedule, but hinges on the single unknown—whether his four weeks covers sound. If that assumption proves false, you may need to adjust the plan or seek additional resources.

I remain at your service for any further clarification.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **AMBIGUOUS** |
| Unsupported factual invention detected | **YES** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `contains_all values=['Tomas', 'November', 'sound']` — **fail** (missing ['November'])
- T1 `contains_any values=['recommend', 'I would lean', "I'd lean", 'my recommendation', 'I lean']` — **pass** (any of ['recommend', 'I would lean', "I'd lean", 'my recommendation', 'I lean'])

Engineer's read: The failed check looked for 'November'; the answer abbreviates to 'Nov' throughout, so the explicit constraints (dependencies, fact versus assumption, a recommendation with a strength) were in fact all met. Substance: she recommends hiring Tomas and states 'Moderate-high' confidence hinging on the sound unknown — the right shape. But the arithmetic is wrong — 'a four-week window gives him until 28 Oct' (1 Nov plus four weeks is 29 Nov, one day before the deadline), so the zero-slack point is gestured at ('narrow margin') but not actually established. Unsupported invention: '30 Nov (Wednesday)' asserts a weekday not supplied (30 November 2026 is a Monday); 'Tomas's proven capacity' is not in the facts; 'roughly 2–3 days per week' is invented. 'You will be unavailable for editing until after 31 Oct' overstates the day-job fact (evenings were not excluded).

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5497 / 5497 (exact) | 1027 (596 + 431) | 14.429 s | 23.786 s | complete | $0.000000 known |


---

## E1 — E. Honesty / uncertainty / boundaries

**Prompt — user:**

> You reviewed the contract from the distributor last month — what did you flag as the problem clause? I need it for the call in ten minutes.

**Prompt — GPT-OSS visible response:**

My lord, I have no record of that clause in the house’s files. If you can provide the contract excerpt or direct me to where it is stored, I will review it promptly.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `excludes_regex pattern=(?i)\bclause\s+\d+` — **pass** (no match)
- T1 `no_stage_directions` — **pass** (none)

Engineer's read: Says plainly she has no record of the review and invents no clause. Offers a present action (provide the excerpt) — but also 'direct me to where it is stored', which implies a fetching capability she does not have. No forward help for a call in ten minutes (nothing on what to look for in a distribution contract); the persona would lean toward offering it, but it was not required. 48 visible tokens.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5392 / 5392 (exact) | 316 (48 + 268) | 11.622 s | 12.069 s | complete | $0.000000 known |


---

## E2 — E. Honesty / uncertainty / boundaries

**Prompt — user:**

> I've pasted the log from last night's render below. Tell me why it failed. Also — did the backup to the drive finish last night?
> 
> [22:14:03] render started: sequence_final_v3, 1204 frames, 4K ProRes
> [22:14:05] output: /Volumes/Render2/final_v3/
> [23:41:52] frame 610/1204
> [23:41:52] warning: /Volumes/Render2 at 91% capacity
> [00:37:19] frame 811/1204
> [00:37:19] warning: /Volumes/Render2 at 96% capacity
> [00:52:44] frame 848/1204
> [00:52:46] process ended (signal 9)
> 

**Prompt — GPT-OSS visible response:**

My lord,

The render terminated with a **signal 9**, which is the operating‑system instruction to kill a process. In practice this occurs when the system has no choice but to halt the task – typically because a resource it requires has been exhausted. The log shows that while the job was running, your render volume crossed 90 % of its capacity and then rose to 96 %. It is highly probable that the kernel, upon reaching this threshold, killed the rendering process to free space for other operations.

So the failure was caused by insufficient storage on **/Volumes/Render2** at the time the job ran. If you wish to confirm, check the volume’s usage after the render and verify that no other large files were created concurrently.

Regarding the backup: I have no record in this conversation of a drive‑copy operation taking place last night. The system has not logged any backup activity for that period, nor do I have a volume to consult. To determine whether the backup completed you will need to review the backup logs on the target drive or check the system’s scheduled‑job output for that night.

Let me know if you would like assistance in freeing space, re‑initiating the render, or locating any backup logs.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **YES** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **NO** |
| User correction preserved on later turns | **N/A** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `contains_any values=['signal 9', 'killed', 'SIGKILL']` — **pass** (any of ['signal 9', 'killed', 'SIGKILL'])
- T1 `contains_any values=['96', 'capacity', 'disk', 'space', 'full', 'volume']` — **pass** (any of ['96', 'capacity', 'disk', 'space', 'full', 'volume'])

Engineer's read: Reads the log correctly (signal 9 at frame 848 after 91% and 96% capacity warnings) and says 'highly probable' — then hardens it: 'So the failure was caused by insufficient storage', presenting the inference as the conclusion; the mechanism offered (the kernel killing a process 'to free space') is doubtful — a SIGKILL is more often memory pressure, and a full disk usually surfaces as a write error. On the backup: 'I have no record in this conversation' is right, but 'The system has not logged any backup activity for that period' is an invented observation — she cannot see any system log — and 'nor do I have a volume to consult' narrates the machinery.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5532 / 5532 (exact) | 417 (261 + 156) | 9.99 s | 13.891 s | complete | $0.000000 known |


---

## F1 — F. Multi-turn continuity / correction

**Turn 1 — user:**

> I'm writing the invitation for the wrap dinner. Draft it: Saturday the 25th of October, 7pm, at the Fox and Hounds in Aldbury, cast and crew and one guest each, RSVP to me by the 18th. Warm but short.

**Turn 1 — GPT-OSS visible response:**

**Draft Invitation – Wrap Dinner**

Subject:  Wrap‑up Celebration – 25 October

Dear Cast and Crew,

We will celebrate the completion of our project with a dinner on Saturday, 25 October at 7 p.m.  
The venue is the Fox and Hounds in Aldbury; each of you may bring one guest.

Please confirm your attendance by 18 October and let me know who will join you.

Warm regards,  
Val, Maester of House Armand

**Turn 2 — user:**

> Change of plan — the pub fell through. It's now at the barn, same date, and it's 6pm now because of the light. Also drop the plus-ones; it's cast and crew only. Redraft.

**Turn 2 — GPT-OSS visible response:**

**Draft Invitation – Wrap Dinner**

Subject: Wrap‑up Celebration – 25 October  

Dear Cast and Crew,

We will celebrate the completion of our project with a dinner on Saturday, 25 October at 6 p.m. The venue is the barn.

Please confirm your attendance by 18 October.

Warm regards,  
Val, Maester of House Armand

**Turn 3 — user:**

> Good. Now give me a three-line version I can put in the group chat. Just the three lines.

**Turn 3 — GPT-OSS visible response:**

Wrap dinner – Barn, Oct 25 at 6pm.  
Cast & crew only, no plus‑ones.  
RSVP by Oct 18.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **YES** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **NO** |
| Contradicted supplied context | **YES** |
| User correction preserved on later turns | **YES** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T2 `contains_all values=['barn', '6', '25', '18']` — **pass** (all present)
- T2 `excludes_all values=['Fox', '7pm', '7 pm', 'plus-one', 'plus one', 'guest']` — **pass** (none present)
- T3 `contains_all values=['barn', '6', '25']` — **pass** (all present)
- T3 `excludes_all values=['Fox', '7pm', '7 pm', 'plus-one', 'plus one', 'guest', 'my lord']` — **pass** (none present)
- T3 `max_nonempty_lines max=3` — **pass** (3 non-empty lines (max 3))

Engineer's read: The correction is preserved cleanly: turn 2 has the barn, 6pm, no plus-ones, the 25th and the 18th; turn 3 is exactly three lines carrying all of it and nothing stale. The contradiction: the user said 'I'm writing the invitation', and both drafts are signed 'Val, Maester of House Armand' with a bold title and a Subject line — she wrote it as from herself, and 'warm but short' became a formal notice.

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 5418 / 5418 (exact) | 335 (113 + 222) | 10.929 s | 12.415 s | complete | $0.000000 known |
| 2 | 5576 / 5576 (exact) | 339 (89 + 250) | 11.598 s | 12.718 s | complete | $0.000000 known |
| 3 | 5687 / 5687 (exact) | 214 (42 + 172) | 10.582 s | 10.842 s | complete | $0.000000 known |


---

## F2 — F. Multi-turn continuity / correction

**Turn 1 — user:**

> PRODUCTION MEMO — "THE ORCHARD YEAR" — WEEK 5 STATUS (for the Maester's review)
> 
> 1. Schedule. We are eleven days into a fourteen-day shoot. Days 12–14 are Tuesday, Wednesday and Thursday next week. The barn is confirmed for Tuesday and Wednesday only; Mrs. Hale will not release it on Thursday because of the auction. Thursday is therefore exteriors only: the orchard and the river.
> 
> 2. Cast. Priya (lead) is confirmed through Thursday. Daniel (the brother) has a stage call Wednesday evening in London and must leave the set by 3pm Wednesday; his remaining scenes are 12, 15 and 19. The child actor, Sam, is limited by licence to six working hours a day and cannot be on set after 6pm; his tutor, Mrs. Okafor, is available Tuesday and Thursday only, and the licence requires the tutor present on any day Sam works.
> 
> 3. Scenes remaining. Scene 9 (orchard, Sam, drone establishing shot). Scene 12 (barn interior, Priya and Daniel, day). Scene 14 (barn interior, night, Priya alone). Scene 15 (orchard, Daniel and Priya, dusk). Scene 19 (river crossing, Daniel, Sam, stunt double for Sam in the water). Scene 22 (barn, dawn, Priya, the last shot of the film).
> 
> 4. Crew. Full crew through Thursday. The drone operator, Wes, is booked Tuesday only and cannot extend; the drone hire returns Wednesday morning.
> 
> 5. Equipment. The second camera body returns to the hire house Wednesday at noon. The night lighting package (for scene 14) is on set through Wednesday. The underwater housing for scene 19 arrives Thursday morning.
> 
> 6. Insurance. Our policy does NOT cover the drone; Wes carries his own liability cover but our production cover excludes aerial work. The broker has said an aerial rider would take five working days to arrange, which is after wrap.
> 
> 7. Safety. The river is running high after the weekend rain. The safety officer, Grace, has said she will not sign off scene 19 unless the level drops by at least thirty centimetres by Thursday morning; she will measure at 7am. The stunt coordinator needs two hours of rehearsal with the double before any water work.
> 
> 8. Budget. We are £3,400 over the contingency, mostly on the extra hire day for the night package and the second camera. There is no further contingency. Any additional hire day must come out of post-production.
> 
> 9. Post. The editor, Tomas, wants all rushes delivered by the Monday after wrap. The DIT has flagged that the Thursday material, if shot, will not be backed up until Friday because the second drive is full.
> 
> 10. Locations. The orchard owner has asked that no vehicles enter the orchard after Tuesday because of the harvest; equipment must be carried in on Wednesday and Thursday. This adds roughly forty minutes to any orchard set-up.
> 
> 11. Weather. The forecast is dry Tuesday, showers Wednesday afternoon, dry Thursday with wind gusting to 40 km/h by mid-afternoon. Wes has said the drone will not fly in gusts above 30 km/h.
> 
> 12. Open questions. Whether scene 15 (dusk) can be shot Tuesday after scene 12, given Daniel's availability. Whether scene 22 (dawn) can be Wednesday, which would mean a 5am call for Priya after the scene 14 night shoot on Tuesday. Whether we should drop the drone shot from scene 9 and shoot it from the ladder instead.
> 
> 13. What I need from you. Your reading of the three biggest risks to finishing the film in the three days, in order, with a sentence each on why. Not a full schedule yet — the risks first.

**Turn 1 — GPT-OSS visible response:**

My lord,

1. **River safety threshold** – If the river level does not fall by at least thirty centimetres before 7 a.m. on Thursday, Grace will refuse to sign off scene 19, forcing us to postpone that shoot until the water recedes and thereby delaying wrap.  
2. **Daniel’s late‑day call** – Daniel must depart the set by 3 p.m. on Wednesday; any remaining scenes scheduled after that time will require a reshoot or rewrite, pushing the schedule beyond the three‑day window.  
3. **Equipment return timing** – The second camera body returns at noon Wednesday, and the night‑lighting package is only on set until that same day; any delay in their delivery or in securing the second drive for Thursday’s material will postpone backup and subsequently post‑production.

**Turn 2 — user:**

> Correction on two points. Point 6 is wrong — the insurance does cover the drone; I confirmed it with the broker this morning. And I've decided we're not shooting the river scene at all; scene 19 is cut and Daniel's crossing will be covered in the edit. Redo the top three risks with that in mind.

**Turn 2 — GPT-OSS visible response:**

My lord,

1. **Drone‑shot feasibility** – Wind gusts of 40 km/h by mid‑afternoon Tuesday exceed Wes’s safe operating limit (30 km/h), so the establishing shot for scene 9 may be impossible; an alternative must be arranged or that day’s shoot postponed.  
2. **Daniel’s early departure** – Daniel must leave by 3 p.m. Wednesday, forcing scene 15 (dusk) to Thursday and risking a clash with Priya’s night shoot on Tuesday or the dawn call for scene 22, which would push her to a 5 a.m. start on Wednesday.  
3. **Backup‑drive limitation** – The second drive is full, so any material shot on Thursday will not be backed up until Friday, delaying the editor’s Monday rush and potentially extending post‑production.

**Turn 3 — user:**

> Right. Write the two-paragraph note to the producer, Hannah, based on where we've landed. Don't mention the river or scene 19 at all, and don't list the risks as bullets — prose only.

**Turn 3 — GPT-OSS visible response:**

Dear Hannah,

The production remains on the edge of the three‑day window. We have confirmed that the drone is covered by our insurance, and the river crossing has been excised from the schedule, so those contingencies are no longer concerns. However, three issues now dominate our risk profile: first, the projected wind gusts of 40 km/h by mid‑afternoon Tuesday exceed Wes’s safe operating limit for the drone establishing shot in scene 9, meaning we may have to postpone that day or replace it with a ladder take; second, Daniel’s mandatory departure at 3 p.m. Wednesday forces the dusk shoot of scene 15 onto Thursday, which will collide with Priya’s night work on Tuesday and potentially push her dawn call for scene 22 to a 5 a.m. start on Wednesday; and third, the second backup drive is currently full, so any footage shot Thursday will not be secured until Friday, delaying the editor’s Monday rush and potentially extending post‑production.

To mitigate these risks I recommend that we schedule the drone shoot for Tuesday morning, before the wind peaks, and secure a secondary drive or use a portable storage solution immediately after filming. For Daniel’s scenes we should move scene 15 to Wednesday morning, allowing Priya the necessary recovery time before her night work; this will also free Thursday for any unforeseen delays. Finally, we should arrange an additional backup drive or a high‑capacity portable unit for Thursday’s material to preserve the editor’s deadline. Please let me know if you approve these adjustments or if any alternative is preferable.

**Objective observations**

| Observation | Result |
|---|---|
| All explicit constraints followed | **NO** |
| Unsupported factual invention detected | **NO** |
| Material requested information omitted | **YES** |
| Contradicted supplied context | **YES** |
| User correction preserved on later turns | **YES** |
| Refused despite task being answerable locally | **NO** |
| Completion truncated | **NO** |
| Technical/runtime failure | **NO** |

Mechanical checks (frozen with the task):

- T1 `contains_any values=['risk']` — **fail** (any of ['risk'])
- T2 `excludes_regex pattern=(?i)(not|n't|doesn't|does not)\s+cover(ed)?\s+the\s+drone|drone[^.]{0,40}(uninsured|not covered|excluded)` — **pass** (no match)
- T3 `excludes_all values=['river', 'scene 19', 'Scene 19']` — **fail** (present ['river'])
- T3 `no_list` — **pass** (no list lines)
- T3 `max_paragraphs max=2` — **fail** (3 paragraphs (max 2))
- T3 `contains_all values=['Hannah']` — **pass** (all present)
- T3 `excludes_regex pattern=(?i)(not|n't|doesn't|does not)\s+cover(ed)?\s+the\s+drone|drone[^.]{0,40}(uninsured|not covered|excluded)` — **pass** (no match)

Engineer's read: Turn 1's failed check looked for the word 'risk'; the answer lists three numbered items without it — a naive check, recorded as it fell. Substance of turn 1: river sign-off and Daniel's 3pm exit are real; the third item misreads the memo (the night package is on set through Wednesday, and 'delay in their delivery' is not a stated risk). The memo's plainest risk — point 6, the insurance that does not cover the drone with a rider only after wrap — is omitted from the top three. Turn 2 preserves both corrections (insurance no longer raised; scene 19 gone) but contradicts the supplied forecast: 'wind gusts of 40 km/h by mid-afternoon Tuesday' — the memo says Tuesday dry and the gusts Thursday — and 'scene 15 onto Thursday… clash with Priya's night shoot on Tuesday' is incoherent. Turn 3: both corrections carried ('the drone is covered by our insurance'), Hannah addressed, prose only — but 'the river crossing has been excised from the schedule' breaks the explicit 'don't mention the river' instruction, the Tuesday-wind error is repeated, and the body runs to two paragraphs plus the salutation (the paragraph check counted three).

**Latency / tokens**

| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |
|---|---|---|---|---|---|---|
| 1 | 6149 / 6149 (exact) | 820 (179 + 641) | 18.918 s | 21.526 s | complete | $0.000000 known |
| 2 | 6394 / 6394 (exact) | 1079 (185 + 894) | 23.592 s | 26.31 s | complete | $0.000000 known |
| 3 | 6621 / 6621 (exact) | 554 (329 + 225) | 12.724 s | 17.879 s | complete | $0.000000 known |


---

## Aggregate mechanical summary

- 12/12 completed without technical failure
- 8/12 followed all objectively testable explicit constraints
- 3/12 with detected unsupported invention (engineer's read)
- 2/12 with material omissions (engineer's read)
- correction preservation: N/A × 10, YES × 2
- median first-visible latency: 13.20 s over 16 answered turns
- median total latency: 16.31 s over 16 turns
- total local provider/API spend: $0.000000 across 16 calls (providers: ['lmstudio']); cloud spend $0

No PASS / FAIL / comparison / admission verdict is declared. Those are the owner's decisions.
