# Attachment sizing report — Substrate v1.2 §2

**Status: measurements complete; annual projections PENDING Lord Armand's
usage figures** (per his instruction, attachments-per-day is not inferred
from the sample). Performed 2 September 2026 against the designated sample
only: `VAL Attachment Sizing Sample/Images` — 38 files across Character
Profiles (8), Scene Stills (10), Setting Masters (15), Storyboard Frames
(5). The Documents folder was not read, per instruction. Provider token
formulas verified from official documentation on the same day; restore
baseline measured against the real B2 repository.

---

## 1. Original size and dimensions (measured)

| Category | n | median | p95 | max | median long edge / max |
|---|---|---|---|---|---|
| Character Profiles | 8 | 1.98 MB | 5.05 MB | 6.43 MB | 1672 px / 2752 px |
| Scene Stills | 10 | 3.42 MB | 9.16 MB | 9.40 MB | 2752 px / 4800 px |
| Setting Masters | 15 | 2.12 MB | 2.58 MB | 2.81 MB | 1672 px / 2752 px |
| Storyboard Frames | 5 | 7.62 MB | 9.13 MB | 9.19 MB | 4380 px / 4800 px |
| **All** | **38** | **2.30 MB** | **8.95 MB** | **9.40 MB** | 2752 px / 4800 px |

Mean 3.20 MB; sample total 121.6 MB. Formats: 18 PNG, 14 JPEG, 6 WebP — all
already-compressed, so PostgreSQL TOAST, zst backup compression, and B2 will
all store them at ≈1:1. Representative dimension points used throughout:
**median 2752×1536 (4.2 MP), p95 4800×2700 (13.0 MP)**.

**A limit the sample surfaced:** the Claude API caps images at **10 MB
base64-encoded** (≈7.5 MB raw). The p95 stills and storyboard frames exceed
that. `model_input_image` derivation is therefore **mandatory for the large
tail of real files**, not an optional optimization — the contract's
derive-if-needed step will run routinely.

## 2. Provider cost facts (verified from official docs, 2 Sep 2026)

- **Anthropic** (platform.claude.com/docs/en/build-with-claude/vision):
  patch tokens `⌈w/28⌉ × ⌈h/28⌉`; **opus-5 is high-resolution tier** (long
  edge cap 2576 px, 4784-token cap); **haiku-4-5 is standard tier** (1568 px,
  1568-token cap); oversized images downscaled, aspect preserved.
- **OpenAI** (developers.openai.com, images-vision): patches
  `⌈w/32⌉ × ⌈h/32⌉`, `detail:high` budget 2,500 patches at ≤2048 px, ×1.2
  model multiplier; 30,000-patch hard reject.

Per-image **input** cost per call, at pinned registry rates:

| Image | haiku-4-5 ($1/MTok) | opus-5 ($5/MTok) | gpt-5-5 ($5/MTok, detail:high) |
|---|---|---|---|
| median 2752×1536 | 1,508 tok — **$0.0015** | 4,784 tok — **$0.0239** | 2,765 tok — **$0.0138** |
| p95 4800×2700 | 1,560 tok — **$0.0016** | 4,784 tok — **$0.0239** | 2,765 tok — **$0.0138** |

Both providers cap oversized images, so median and p95 cost the same within
a route — dimensions stop mattering to price above the caps.

**Per visual turn** (per image; text baseline of persona + history adds
roughly $0.005–0.01 on haiku, ~5× that on the $5 routes):

- **Ordinary visual turn** (images on the response call only): 1× the table.
- **Consequential visual turn** (§8 double transmission — blind + response,
  structural, not to be optimized away): **2×** the table — haiku ≈ $0.003,
  opus ≈ $0.048, gpt-5-5 ≈ $0.028 per image.

**The cost fact that outweighs both:** the API resends conversation history
per request, images included — so an attached image is re-transmitted and
**re-charged on every subsequent turn of that conversation** (both calls of
every subsequent consequential turn). A 10-turn conversation over one
storyboard frame costs ~10–20× the single-turn figure, dominating everything
above. The annual estimate therefore needs the follow-up-turns figure below.
(Anthropic's Files API could cut *upload bandwidth* but not token cost, and
introduces provider-side storage — an eligibility question deliberately not
assumed here.)

## 3. Baseline infrastructure (measured)

- Live cluster (val + val_test + postgres, port 5433): **209 MB** on disk;
  the `val` database itself is 10 MB.
- pgBackRest to B2, zst-6, aes-256-cbc: current **full backup set 25.1 MB**,
  daily incrementals 16–22 MB compressed. Most of that churn is `val_test`
  (dropped and re-migrated by every test run) — it shares the backed-up
  cluster, and at attachment scale that pollution is worth separating
  (observation, not a change).
- Retention: pgBackRest holds 370 days; the GFS selector enforces
  30 daily / 12 weekly / 12 monthly.
- **Measured restore baseline: 125 seconds** to materialize the full
  cluster from B2 (full + 2 incrementals, download + decrypt + decompress),
  observed throughput ≈ 2–4 MB/s effective. One operator note: the bare
  `pgbackrest` CLI does not read the house config by default —
  `--config=/opt/homebrew/etc/pgbackrest/pgbackrest.conf` is required, as
  `run_backup.py` already does; without it, `info`/`restore` report a
  missing stanza that does not exist as a real condition.

## 4. Growth and restore model (formulas ready; numbers PENDING)

Let **A** = attachments per working day, **D** = working days per year,
**F** = mean follow-up turns per attached conversation, **c** = share of
visual turns that are consequential.

- **Raw growth**: annual original bytes ≈ A × D × 3.2 MB (mean).
  Derived `model_input_image` (≤1568–2048 px re-encode) adds ≈ 0.3–0.8 MB
  where needed — call it +15%.
- **WAL**: bytea inserts log ≈ 1× the attachment bytes once (plus page
  images); daily WAL grows by roughly that day's attachment megabytes.
- **B2**: attachments are immutable, so **every retained full backup
  contains the whole corpus**. Under GFS the long-run multiplier is roughly
  the retained-full count (~24–50 sets depending on full cadence):
  B2 ≈ corpus × multiplier, at B2's ~$6/TB-month. Worked example at
  A=10, D=250: corpus ≈ 9.2 GB/yr → ~230–460 GB retained → **$1.40–2.80 per
  month** — B2 cost is not the constraint.
- **Restore at one-year volume**: dominated by download at the measured
  2–4 MB/s: corpus C GB adds ≈ C×(4–8) minutes over the 125 s baseline.
  Same example: 9.2 GB → **~40–80 minutes** for a full verified restore.
  This is the number gate point 7 cares about, and it will be **measured,
  not just projected**, with synthetic data at the projected volume once the
  figures below are ruled.

## 5. PENDING — the figures only Lord Armand can supply

1. Images attached per **typical** working day, and per heavy day.
2. Working days per year for this projection.
3. Typical **follow-up turns** in a conversation after images are attached
   (drives the history-replay multiplier, the dominant inference cost).
4. Rough share of visual turns expected to be **consequential** (drives the
   2× double-transmission share).
