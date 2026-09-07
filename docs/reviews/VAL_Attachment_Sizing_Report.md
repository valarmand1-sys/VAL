# Attachment sizing report — Substrate v1.2 §2

**Status: complete. Returned for Lord Armand's byte-store ruling.**
PostgreSQL remains the only candidate byte store; this report supplies the
measured and projected figures the ruling needs and recommends nothing
architectural.

Measurements were performed 2–3 September 2026 against the designated
sample only: `VAL Attachment Sizing Sample/Images` — 38 files across
Character Profiles (8), Scene Stills (10), Setting Masters (15), Storyboard
Frames (5). The Documents folder was not read, per instruction. Provider
token formulas were verified from official documentation on 2 September;
restore was measured against the real B2 repository at both the current
volume and the projected one-year volume.

Sizes below are decimal (1 MB = 10⁶ bytes, 1 GB = 10⁹ bytes).

---

## 0. Inputs — Lord Armand's figures (3 September 2026)

| Figure | Value | Standing |
|---|---|---|
| New unique images per typical working day | **13** | his own statement |
| New unique images per heavy working day | **25** | his own statement |
| Working days per year | **250** | his own statement |
| Follow-up sends per attached conversation | **3** | **planning estimate** |
| Share of visual turns that are consequential | **25%** | **planning estimate** |

Definitions he fixed: a *new unique image* is a first ingestion that creates
a blob. Re-attaching an already-stored image to a later message is
re-association: a transmission, not storage. Nothing in this report infers
attachments-per-day from the sample's file count.

## 1. Originals — size and dimensions (measured)

| Category | n | median | p95 | max | median long edge / max |
|---|---|---|---|---|---|
| Character Profiles | 8 | 1.98 MB | 5.05 MB | 6.43 MB | 1672 px / 2752 px |
| Scene Stills | 10 | 3.42 MB | 9.16 MB | 9.40 MB | 2752 px / 4800 px |
| Setting Masters | 15 | 2.12 MB | 2.58 MB | 2.81 MB | 1672 px / 2752 px |
| Storyboard Frames | 5 | 7.62 MB | 9.13 MB | 9.19 MB | 4380 px / 4800 px |
| **All** | **38** | **2.30 MB** | **8.95 MB** | **9.40 MB** | 2752 px / 4800 px |

Mean **3.20 MB**; sample total 121.6 MB. Formats: 18 PNG, 14 JPEG, 6 WebP —
all already-compressed, so PostgreSQL TOAST, zst backup compression, and B2
all store them at ≈1:1. Representative dimension points used throughout:
**median 2752×1536 (4.2 MP), p95 4800×2700 (13.0 MP)**.

## 1a. Derived `model_input_image` representations (measured)

Every original was re-encoded to JPEG at each provider tier's long-edge cap,
aspect preserved, to measure what the contract's derive-if-needed step
would actually store:

| Tier | Cap | Originals exceeding the cap | Derived mean | median | max |
|---|---|---|---|---|---|
| Anthropic high-res (opus-5) | 2576 px | **22 of 38** | **0.92 MB** | 0.89 MB | 1.98 MB |
| Anthropic standard (haiku-4-5) | 1568 px | **35 of 38** | **0.42 MB** | 0.41 MB | 0.80 MB |

Weighted by how often each tier's representation is needed, derived bytes
come to **≈0.92 MB per ingested image**, i.e. about 29% on top of the
original.

**Two facts the sample established:**

- The Claude API caps images at **10 MB base64-encoded** (≈7.5 MB raw).
  **6 of 38 originals exceed that.** Derivation is therefore mandatory for
  the large tail of real files, not an optional optimization.
- 35 of 38 originals exceed the standard-tier cap and 22 of 38 exceed the
  high-res cap, so the derive step runs for nearly every image on the
  cheap route and for most on the expensive one.

## 2. Provider cost facts (verified from official docs, 2 Sep 2026)

- **Anthropic** (platform.claude.com/docs/en/build-with-claude/vision):
  patch tokens `⌈w/28⌉ × ⌈h/28⌉`; **opus-5 is high-resolution tier** (long
  edge cap 2576 px, 4784-token cap); **haiku-4-5 is standard tier** (1568 px,
  1568-token cap); oversized images downscaled, aspect preserved.
- **OpenAI** (developers.openai.com, images-vision): patches
  `⌈w/32⌉ × ⌈h/32⌉`, `detail:high` budget 2,500 patches at ≤2048 px, ×1.2
  model multiplier; 30,000-patch hard reject.

Per-image **input** cost per transmission, at pinned registry rates:

| Image | haiku-4-5 ($1/MTok) | opus-5 ($5/MTok) | gpt-5-5 ($5/MTok, detail:high) |
|---|---|---|---|
| median 2752×1536 | 1,508 tok — **$0.0015** | 4,784 tok — **$0.0239** | 2,765 tok — **$0.0138** |
| p95 4800×2700 | 1,560 tok — **$0.0016** | 4,784 tok — **$0.0239** | 2,765 tok — **$0.0138** |

Both providers cap oversized images, so median and p95 cost the same within
a route — dimensions stop mattering to price above the caps.

**What multiplies the per-transmission figure:**

- **Consequential visual turns** transmit the image twice (§8 of the
  contract — blind position and response, structural, not to be optimized
  away).
- **History replay.** The API resends conversation history per request,
  images included, so an attached image is re-transmitted and re-charged
  on every subsequent turn of that conversation. The contract already
  accounts for this per call, not per attachment: each transmission is its
  own `model_call_image_inputs` row. This is the dominant inference cost and
  is why the follow-up figure matters more than the per-image price.
  (Anthropic's Files API could cut upload bandwidth but not token cost, and
  introduces provider-side storage — an eligibility question deliberately
  not assumed here.)

## 3. Infrastructure — measured

### 3a. Current baseline

- Live cluster (val + val_test + postgres, port 5433): **209 MB** on disk;
  the `val` database itself is 10 MB.
- pgBackRest to B2, zst-6, aes-256-cbc: current **full backup set 25.1 MB**,
  daily incrementals 16–22 MB compressed. Most of that churn is `val_test`
  (dropped and re-migrated by every test run) — it shares the backed-up
  cluster, and at attachment scale that pollution is worth separating
  (observation, not a change).
- Retention: pgBackRest holds 370 days; the GFS selector enforces
  30 daily / 12 weekly / 12 monthly.
- **Measured restore of the current cluster: 125 seconds** (full + 2
  incrementals, download + decrypt + decompress).
- Operator note: the bare `pgbackrest` CLI does not read the house config
  by default — `--config=/opt/homebrew/etc/pgbackrest/pgbackrest.conf` is
  required, as `run_backup.py` already does; without it, `info`/`restore`
  report a missing stanza that does not exist as a real condition.

### 3b. Restore at one-year typical volume (measured, not projected)

A synthetic corpus of **4,438 random 3 MB blobs (13 GB)** was loaded into a
scratch PostgreSQL cluster, backed up to the real B2 repository under a
scratch stanza with the house configuration (zst, aes-256-cbc), restored
to a second directory, started, and verified. The cluster measured 27.2 GB
on disk because the bulk load left 14 GB of write-ahead segments
unrecycled, so the backup set was **26.1 GB** — roughly double the corpus,
which makes these figures conservative for the corpus size.

| Measurement | Result |
|---|---|
| Restore, download + decrypt + decompress, 26.1 GB set | **10,936 s (3 h 02 min)** |
| Restore to a usable, started cluster | same: no recovery replay was needed on an offline backup |
| Effective restore throughput | **≈ 2.4 MB/s** |
| Verification | 4,438 rows, 13 GB, **0 of 4,438 stored digests failed to recompute** |
| Backup upload | not cleanly measured: the upload was interrupted once and resumed, and the wall time of the resumed run (41,559 s) includes the resumption; at the observed throughput a 26 GB set is of the same order as the restore |

Scaling the measured throughput to the §4 corpus figures (the restore
scales with the backup-set size, and the set holds the whole corpus):

| Corpus at end of year one | Restore at 2.4 MB/s |
|---|---|
| Typical, 13.4 GB | **≈ 1 h 35 min** |
| Heavy, 25.7 GB | **≈ 3 h** |

Measured on the postgresql@16 binaries that the shell path resolves to;
the live cluster is postgresql@18. Only transfer and verification were
under measurement, and those do not depend on the server version. The
scratch stanza was deleted from the repository afterwards and the live
stanza reports `status: ok`.

## 4. Annual projections from his figures

Model: images/yr = A × 250. Corpus = originals (3.20 MB mean) + derived
(0.92 MB mean). Transmissions/yr = images × (1 + 3 follow-ups) × (1 + 0.25
consequential double). B2 = corpus × retained-full multiplier: ≈18× at the
end of year one (earlier fulls are smaller than the final corpus), ≈24×
once every retained full holds the whole corpus. B2 at ~$6/TB-month.

| | Typical (13/day) | Heavy (25/day) |
|---|---|---|
| New unique images / yr | 3,250 | 6,250 |
| Originals stored / yr | 10.4 GB | 20.0 GB |
| Derived representations / yr | 3.0 GB | 5.7 GB |
| **Corpus growth / yr** | **13.4 GB** | **25.7 GB** |
| Daily WAL from attachments | ~54 MB | ~103 MB |
| B2 retained, end of year one | ~240 GB → **$1.45 / month** | ~460 GB → **$2.78 / month** |
| B2 retained, steady state (24×) | ~320 GB → $1.93 / month | ~620 GB → $3.71 / month |
| Image-bearing transmissions / yr | 16,250 (65 / working day) | 31,250 (125 / working day) |
| Image input cost / yr — haiku-4-5 | **$25** | **$47** |
| Image input cost / yr — opus-5 | **$389** | **$748** |
| Image input cost / yr — gpt-5-5 | **$225** | **$432** |

The inference rows are image-input tokens only; the text baseline of each
call (persona, history, output) is unchanged by attachments and is not
counted here. The rows are per-route alternatives, not additive — actual
spend depends on how selection distributes visual turns across routes.

Sensitivity to the two planning estimates: transmissions scale linearly with
(1 + follow-ups) and with (1 + consequential share). Doubling follow-ups
to 6 raises every inference row by 75%; halving the consequential share to
12.5% lowers them by 10%. Storage rows do not depend on either estimate.

## 5. What the numbers say about PostgreSQL as the byte store

Stated as facts for the ruling, not as a recommendation.

- **Storage scale is small.** One year at heavy use is ~26 GB in the
  cluster; five years is ~130 GB. TOAST stores each blob out-of-line and
  already-compressed data at ≈1:1; nothing here approaches a PostgreSQL
  limit.
- **Backup carries the whole corpus in every full.** Attachments are
  immutable, so each Sunday full re-uploads the entire corpus, and every
  retained full holds all of it. That is what makes B2 ~18–24× the corpus —
  still under $4 per month at heavy use. B2 cost is not the constraint.
- **Restore time is the constraint that grows.** Measured at about 2.4 MB/s
  from B2, a restore is roughly **1 h 35 min at typical year-one volume and
  3 h at heavy** (§3b), against 125 s today. It scales with corpus size.
  This is the number gate point 7 (backup restore verified) will be
  measured against as the corpus grows, and it is the figure to hold
  against any recovery-time expectation.
- **Weekly full upload time grows the same way.** The upload was not
  cleanly timed (§3b), but at the observed transfer rate the Sunday full
  will take hours, not minutes, by the end of year one.
- **`val_test` shares the backed-up cluster.** At attachment scale its
  drop-and-remigrate churn is a larger share of each incremental than the
  real data. Observation only.
- **Not measured here:** the Documents folder (excluded by instruction);
  in-database read latency for serving blobs to the desktop app (no
  consumer exists yet); PostgreSQL 18 specifically — the volume measurement
  ran on the postgresql@16 binaries that the PATH resolves to, since only
  transfer timing was under measurement and that is version-independent.
