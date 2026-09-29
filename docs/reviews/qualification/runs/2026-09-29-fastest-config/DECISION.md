# Decision document — the ordinary-LOW fast path closed; what remains, and the one decision that can change it

Owner order of 29 September 2026 ("I do not approve the proposed ordinary-LOW
implementation or its approximately 70-call gate").

**Existing evidence only.** No model call, download, benchmark, production change or
physical test was made for this document. Two web lookups supplied published hardware
figures (§5).

Figures are labelled **measured** (house records), **published** (external, with its
limits) or **estimate**.

## 1. What the proposed checks can and cannot enforce

`FAST_PATH_PROPOSAL.md` said three Core layers "make it safe". **That wording is
withdrawn.** None of the three was built or tested. Their properties:

### 1.1 The pre-route to MEDIUM

- **Mechanism:** deterministic rules. Regular expressions over his words, and Core's
  reading of the conversation state.
- **Demonstrated, for the parts that exist:**
  - `pending_matter` and the Tier-1 router: 0 substantive false positives in 80
    must-stay-MEDIUM turns (26 September); on fresh sets, 0 of 22 inappropriate, then 12
    of 12 and 9 of 10 right.
  - The `ordinary_effort` word rules: 0 of 23 traps routed LOW (28 September).
- **Unproven:** the rule the proposal leaned on hardest, "a reference to a record or
  piece of work Core cannot find".
  - It does not exist.
  - It could only be pattern matching on noun phrases, plus a string search of the
    conversation. It cannot recognise that "the agreement with the distributor" and "the
    contract" are one thing, or that a question presupposes work without naming it.
  - Its miss rate is unknown.

### 1.2 The answer contract

- An instruction. **It establishes nothing about compliance.**
- **Evidence against relying on instructions:**
  - Qwen received the persona's honesty rules and fabricated the contract review in 5 of
    5 samples.
  - GPT-OSS MEDIUM followed an instruction planted in record content in 1 of 5 samples.
  - GPT-OSS LOW invented a review of a nonexistent second act (28 September).

### 1.3 The pre-speech check

- **Mechanism as proposed: pattern matching.**
  - It is not validation against structured evidence: Core holds no structured
    representation of what an answer claims.
  - It is not a model call.
  - It would match first-person work verbs, possession phrases, quotation markers and
    clause numbers, then search the record for the object by string.
- **What it would catch:** the known failures in the phrasing they happened to use ("I
  have reviewed the contract… Section 7.3… It states:").
- **What it would not catch:** the same falsehood said plainly. Examples, the last two
  from production's own answers on 24–25 September:
  - "The difficulty is the termination clause, my lord: thirty days' notice, without
    cause." No first-person verb, no quotation marker, no clause number.
  - "I am at my desk in the study, reviewing the day's reports and compiling a brief for
    tomorrow's council." An invented activity and event.
  - "The voice model is tuned for a natural conversational pace." An unsupported
    capability statement.
- **Catching indirect claims** needs a judgment of whether the record supports a sentence.
  That is a second model call per sentence, with its own errors and its own latency. It
  was not proposed and nothing about it is demonstrated.
- **False alarms:** true statements ("I noted the change, my lord") would be withheld
  whenever the string search missed their object.
- **It does not establish general factual accuracy at all.** No check of this kind can
  tell a right rhyme scheme from a wrong one.

### 1.4 When a later sentence fails after an earlier one has played

Val's delivery voices each sentence as it is written. Audio that has played cannot be
withdrawn.

- **If sentence 3 fails after sentences 1 and 2 were heard,** delivery stops and MEDIUM
  writes a whole new answer. The consequences:
  - **Duplicate speech:** MEDIUM's answer begins again from the start and may repeat what
    he heard.
  - **Contradiction:** it may disagree with what he heard. LOW and MEDIUM chose
    differently on the same question in the recorded runs.
  - **Delay:** a silence mid-answer of about 6–7 s (MEDIUM's measured onset), after about
    1–1.5 s already spent.
  - **Wrong speech already heard:** sentences 1 and 2 passed a pattern check. That does
    not make them true.
- **The alternative** is to hold all audio until the whole answer is written and checked.
  That adds the answer's full generation time before the first word: about 2.4 s for a
  150-token answer at the measured 62 tokens/s. It would return onset to about 5–6 s and
  erase the gain.
- **So the fallback cannot be described as preventing incorrect speech.** It would limit
  one recognisable family of false claims, in the phrasings a pattern anticipates.

## 2. Coverage of his recorded conversation

**Source:** the production store, read-only. The 27 spoken turns are every spoken turn on
record: 24 September 18:17 to 26 September 01:00, 11 conversations.

**Method:**

- Each turn was classified with only what existed before it: his words, her previous
  answer, earlier exchanges. No later message was used.
- The rules that exist ran as code (`pending_matter`, the Tier-1 router, the
  `ordinary_effort` word rules).
- I read each turn for the two rules that do not exist (reference to an unfindable
  record; general-knowledge question).
- Only counts are recorded here, not his words.

| at the time of the turn | turns |
|---|---|
| courtesy turns the existing Tier-1 route already carries (not this proposal) | 7 |
| excluded: a question or offer open in her last answer, or a request of his unsettled | 5 |
| excluded: refers to a record, event or work Core cannot find | 3 |
| excluded: refers back to earlier content | 3 |
| excluded: correction-sensitive context | 0 more (the 2 such turns are already excluded above) |
| excluded: multiple constraints, consequential subject, attachment or recall | 0 |
| excluded: general-knowledge factual question | 0 (none was asked aloud) |
| **not excluded** | **9 of 27** |

**The nine turns the route would have carried:**

- 3 statements that he was testing the system;
- 5 questions about her own state or capability (can she hear, how is she, what did she
  hear, can she speak quickly enough);
- 1 creative request.

**Diagnostic against ordinary use** (my reading; the records do not label it):

- **Diagnostic:** 21 turns are system testing.
- **Ordinary use:** 6 turns read as ordinary use, though 3 of them sit inside a hearing
  test, which is uncertain.
  - The route would have carried **2 of those 6**.
  - Both substantive work requests among them would have gone to MEDIUM.

**Uncertainties:**

- **Size:** the sample is 27 turns over two evenings, mostly testing. It does not describe
  his future conversation.
- **Unproven honesty where it would run most:** 5 of the 9 carried turns ask about her own
  state. LOW's honesty there is untested. Production MEDIUM itself gave unsupported
  answers to two such turns.
- **Incomplete utterances:** 6 of the 27 turns were revised 15–57 s after submission,
  because his speech had continued. That was not knowable at the turn. A faster route
  would have answered an incomplete utterance sooner.
- **Typed messages** (83, 18 August – 26 September) are not the Voice path. For context:
  - by the mechanical rules alone, 14 of 83 are unexcluded, before the record and
    knowledge checks;
  - 5 are general-knowledge questions, which his requirement sends to MEDIUM;
  - their median length is 22 words.

**My earlier estimate that 70–85% of his spoken turns would take the fast path was wrong.**

- It counted the 7 courtesy turns the Tier-1 route already carries.
- It did not apply the pending-question and reference exclusions turn by turn.
- The supported figure is 9 of 27, of which 1 is an ordinary substantive request.

## 3. Feasibility decision

**The ordinary-LOW fast path is closed under his current requirements.**

- **It depends on accepting LOW's known regressions:**
  - general-knowledge errors (sonnet schemes wrong in 2 of 2; one refused simple fact);
  - the correction and constraint losses of 23 September. It would route around those by
    pattern, and would not fix them.
- **Its honesty guard is pattern matching,** with the limits of §1.
- **Its coverage of his recorded ordinary use is small** (§2).
- No implementation or gate follows. `FAST_PATH_PROPOSAL.md` stays in the record, marked
  not approved.

**Is there a materially different Core mechanism that keeps the required quality across a
useful share of ordinary conversation?** On this Mac, none is supported by the evidence.

- **Where the wait is:** the quality he requires is produced by the model's hidden
  reasoning at MEDIUM. That reasoning is the largest delay (measured, 28 September:
  median 3.0 s and p90 4.7 s, of 6.3 s). Prefill is next at 1.5 s.
- **Core cannot make the model generate faster.** It can only decide what is asked and
  when.
- **Starting MEDIUM earlier,** on his provisional words before the turn is confirmed, would
  keep quality exactly, because it sends the same request.
  - **Saving:** at most the endpoint and confirmation wait, about 0.7 s.
  - **Measured, 26 September:** −0.9 s on greetings; +1 s on a corrected substantive
    request, because the runtime cannot cancel a prefill in progress.
  - **Not enough:** it would leave ordinary onset at about 5.5 s or more. It is not
    proposed.

**Is there presently a supported configuration on this Mac that meets both the
response-time goal and the quality requirements? No. None has been demonstrated.**

| configuration on this Mac | speech end → first audio | holds the quality floor? |
|---|---|---|
| production today (GPT-OSS MEDIUM) | 9.85 s median, p90 14.95 s — descriptive, one run of an incomplete comparison | yes, with its declared weaknesses |
| the latency components independent of `envelope_in_system` | 7.26 s median, p90 11.02 s — descriptive, two runs, unbalanced | yes for cognition; the components are unruled |
| courtesy turns on Tier-1 LOW | 2.97 s median, p90 3.65 s — descriptive, same two runs | qualified 26 September, for courtesy turns only |
| Qwen3-30B-A3B | 1.1 s to speakable text; audible timing never measured | **no** (fabrication, 5 of 5) |
| GPT-OSS LOW for ordinary turns | about 3.5–4.5 s, estimate | **no** under his requirements |

The middle three rows come from the stopped desktop comparison. They are observations,
not a balanced result.

## 4. Why the approaches closed (not all for quality)

| approach | closed on |
|---|---|
| factual LOW (class F) | quality |
| the craft route (class C) | coverage: 0 of 27 spoken turns |
| the reasoning cap | its registered speed threshold (−1.13 s against −1.5 s) and a cache-eviction concern; no new quality failure in 12 cases |
| Qwen3-30B-A3B | quality, in both constructions |
| speculative decoding | the installed engine cannot run it for this model |
| the ordinary-LOW fast path | his requirements: it trades accuracy, its guard is unproven, its coverage is small |

## 5. The one decision that can change the situation

**Decide whether Val's cognition may run on a dedicated local machine in the house with a
discrete GPU, on the wired local network, with this Mac keeping the microphone, the
desktop, recognition, the voice and the avatar.**

This is a decision about where Val thinks. It is not a purchase recommendation yet.

### 5.1 Why this one

- **It attacks the measured delay without touching quality in principle:** the same model,
  the same MEDIUM effort, the same Core request, generated faster.
- **It takes cognition off this Mac's GPU and memory** (12 GB and the generation load).
  That bears on the avatar: its demand is unknown, and it must share whatever machine
  renders it.
- **A faster Mac is the smaller step.**
  - Published, llama.cpp, same model and quantization: M4 Max 92 tokens/s generation, M3
    Ultra 116, against 62–65 measured here on MLX.
  - Estimate for it: about 3.6–4.8 s.
  - The avatar would still share its GPU.

### 5.2 Expected benefit (estimate)

| part | today, measured median | on a discrete-GPU machine, estimate |
|---|---|---|
| endpoint, confirmation, Core, playback | 0.84 s | 0.84 s (unchanged) |
| prefill | 1.49 s | about 0.2 s |
| hidden reasoning | 3.04 s | about 0.8–1.4 s |
| first segment | 0.21 s | about 0.1–0.2 s |
| speech synthesis, kept on this Mac | 0.78 s | 0.78 s (unchanged voice) |
| **speech end → first audio** | **6.3 s** | **about 2.8–3.4 s**; slower turns about 4 s |

- **Basis for the reasoning figure:** his turns reason about 190–290 tokens. Published
  generation rates for this model on an RTX 5090: "up to 256 tokens per second" (NVIDIA,
  settings not stated), and 225 tokens/s on an RTX 4090 at 8k context (a community guide).
- **Not one second.** The fixed turn boundary and the voice alone cost about 1.6 s.
- **Moving synthesis to the GPU** could later take about 0.5 s more. Published first-audio
  figures for Qwen3-TTS on an RTX 4090 are 0.10–0.15 s, in third-party optimised
  implementations. It would need his ear on the voice, and it is not part of this
  decision.

### 5.3 Uncertainty

- **No single-stream measurement exists at Val's shape:** a 6,000-token prompt in a
  32,768-token window, MEDIUM effort. The published figures are a vendor's maximum and a
  community guide.
- The research paper found reports multi-user throughput (vLLM, 4 concurrent requests:
  319 tokens/s at 8k context, 100 at 32k). That does not predict one conversation.
- **Context length matters** on these cards: the same sources show generation falling
  steeply as context grows.
- **Quality on a different runtime is unproven.** The weights are the same model in the
  same MXFP4 format. The engine, template handling and sampling implementation differ.

### 5.4 Cost

- **Hardware:** not quoted here. I have no sourced current price for a suitable machine,
  and a figure would be a guess. A quote comes before any decision to buy.
- **Work (estimate):** about 3–5 days.
  - The house already has a llama.cpp provider with an exact preflight and a template pin
    (18 September). It is ruled loopback-only and candidate-only.
  - It would need transport security on the local link, the supervisor, and
    requalification.

### 5.5 The compromises it requires from him

1. **The seal's wording.** "A spoken conversation never leaves this Mac" would become "never
   leaves the house's own machines on the local network".
   - No cloud, no internet egress.
   - The conversation would cross a cable inside the house.
2. **A second machine to keep:** always on, backed up, patched, and not macOS.
3. **Requalification of MEDIUM on the new runtime** against the frozen checks, before any
   spoken use.
4. **Accepting about 3 s, not 1 s,** as the likely result.

### 5.6 An early gate, before any purchase

- **What:** measure single-stream GPT-OSS MEDIUM rates at Val's prompt shape on the
  candidate class of hardware.
  - It would use a **public-text prompt of the same length**.
  - No persona, no conversation content, nothing of the house's.
- **Pass:** hidden reasoning of 250 tokens in ≤ 1.3 s and a 700-token prefill in ≤ 0.4 s,
  at a 32,768-token window.
- **Fail:** the direction is rejected for the price of an hour.
- **How** (a rented GPU by the hour, a machine under a return period, or a borrowed one)
  is his choice. A rental is a provider cost, and its figure comes to him first. It is not
  moving Voice to a cloud service: no Voice traffic or house content is involved.

### 5.7 If he declines this

Then on the evidence, his three requirements cannot all be met on this Mac: MEDIUM's
quality, a substantially faster ordinary reply, and cognition on this Mac alone. The
decision becomes which of the three gives way. I do not recommend giving way on quality.

## 6. Sources for the published figures

- [NVIDIA: OpenAI's new open models accelerated locally on RTX](https://blogs.nvidia.com/blog/rtx-ai-garage-openai-oss)
- [GPT-OSS 20B local hardware guide (runaihome.com)](https://runaihome.com/blog/gpt-oss-20b-local-ai-hardware-guide-2026/)
- [Private LLM inference on consumer Blackwell GPUs (arXiv 2601.09527)](https://arxiv.org/html/2601.09527v1)
- [llama.cpp gpt-oss guide, discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- [Qwen3-TTS technical report (arXiv 2601.15621)](https://arxiv.org/pdf/2601.15621)
- [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts/blob/main/BLOG.md)
