# VAL — Open Decisions

Only questions that require Lord Armand's decision. Implementation problems
Claude can solve are not listed here; they are in §K of the handoff.

Generated at commit `ccc94e3`, 16 August 2026.

---

## 1. The Anthropic account reports no credit

**Not a decision so much as an action only you can take**, listed here because it
is the single blocker on WP-0.4 and no engineering will clear it.

The key authenticates and lists models — `claude-opus-5`, `claude-sonnet-5`,
`claude-fable-5` — so it is valid and correctly scoped. Only inference is
refused:

```
400 invalid_request_error
"Your credit balance is too low to access the Anthropic API."
request_id: req_011Ce5aYFevxhMfvsywK1gem
```

You said credit was on both accounts, and OpenAI's is working. The likely causes
are credit purchased on a different organisation than the key belongs to, or a
workspace-scoped key without a spend allocation.

**No decision is needed on the code.** Once inference succeeds, the three
remaining WP-0.4 criteria are a single script run.

---

## 2. Should Gemini stay unusable, or should its verifier be built?

**Genuinely your call, and safe to leave as it is.**

Your 15 August ruling was that a Gemini configuration must verify at startup that
its key is attached to paid billing, and fail if it cannot confirm it. Google
exposes no API that reports billing status for a Generative Language API key, so
`verify_paid_billing` fails closed and **always** fails. Gemini therefore cannot
be configured at all. No Gemini entry is in the registry, so nothing is blocked
today.

Three options:

1. **Leave it.** Gemini stays unusable. Costs nothing; two providers is what the
   architecture requires.
2. **Build a real check** against the Cloud Billing API for the project behind the
   key. More moving parts, and needs a GCP project and service-account access.
3. **Rule differently** — e.g. accept a billing-account id recorded in the
   registry as sufficient evidence. **I would advise against this**: it is
   configuration claiming it, which your ruling explicitly rejected.

**Recommendation: option 1** until there is a reason to want Gemini. Nothing is
waiting on it.

---

## 3. Should the interrupt-level machinery arrive before WP-0.10?

**Low stakes; asking because the sequencing is yours.**

The four interrupt levels are specified in `02-partner-systems.md` §5.5 as of the
15 August amendment, with no machinery — as you directed. Level 3 (immediate:
integrity, data loss, security only) is the only one with a plausible Layer 0
consumer: the backup watcher currently alerts through macOS notifications on its
own rather than raising a signal for Val to level.

Doing nothing is defensible — the watcher works, and Val has no interface to
interrupt through until WP-0.10. **Recommendation: leave it.** The natural moment
is WP-0.10, when there is a conversation to interrupt.

---

## Nothing else

No other open question requires your decision. Everything else in §K of the
handoff is either sequenced work or waiting on time to pass.
