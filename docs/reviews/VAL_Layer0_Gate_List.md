# Layer 0 gate list

Standing rule (Lord Armand, 18 August 2026): review happens at the Layer 0
gate, not continuously. A finding that is not tied to a stated acceptance
criterion goes here, not into a corrective round. Items here are neither
defects against accepted criteria nor decisions needed now.

| # | Item | Origin |
|---|---|---|
| 1 | `budget_reservations` transmission marker: a set-once `transmission_started_at` would let restart reconciliation release provably-never-sent holds instead of conservatively expiring them. Requires amending §2.5's enumerated column list — a baseline decision. **Lord Armand's recorded objection, 19 Aug 2026: current inclination is to reject — the marker records the boundary being entered, not transmission occurring, so it does not resolve the indeterminacy it was meant to address.** | WP-0.4 crash-boundary work, 19 Aug 2026 |
| 2 | `GatewayErrorKind` granularity on failed calls is not durable beyond `terminal_state='failed'`. | Closure pass, 18 Aug 2026 |
| 3 | Lexical retrieval limit: a question sharing no vocabulary with the earlier conversation will not recall it. Semantic retrieval needs four recorded decisions (`VAL_Open_Decisions.md` item 10). | WP-0.7 |
| 4 | A provider inventing a new stop reason lands in `UNKNOWN` and fails closed until an adapter mapping entry is added. | Closure corrections, 18 Aug 2026 |
| 5 | Non-conversation callers of `complete()` (WP-0.8+) must branch on `TRUNCATED`/`FILTERED` terminal states. | Closure corrections, 18 Aug 2026 |
| 6 | `MAX_HISTORY_TURNS` has never been exercised by a real >40-turn conversation. | WP-0.7 |
| 7 | Audit for other naive-timestamp boundaries of the shape fixed in `211e59c`: an expression like `date_trunc(..., now() at time zone 'utc')` yields a naive timestamp that PostgreSQL reinterprets in the *session* timezone, so time-window logic that is correct in a UTC session (CI) can be wrong in a local one. The month-boundary instance was found by a calendar accident — the first CI run after the UTC month rolled to 1 September 2026 — not by looking. The audit sweeps every SQL comparison between a timestamptz column and a computed timestamp (raw SQL strings, migrations, triggers, backup/verify scripts), every place a naive Python datetime meets an aware one, and asserts each boundary means the same instant in any session timezone. Lord Armand, 31 Aug 2026. | Month-boundary fix, 211e59c |
