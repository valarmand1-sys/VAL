# Backup

How the authoritative store is backed up, encrypted, watched, and restored.
Mechanism required by `00-charter.md` invariant 35 and `01-architecture.md` §9;
acceptance criteria in `04-layer-0.md` WP-0.3.

**A backup that has never been restored is not a backup.** Everything below
exists to keep that sentence enforceable.

---

## Shape

| | |
|---|---|
| Tool | pgBackRest 2.59.0 |
| Destination | Backblaze B2, bucket `valbackups`, prefix `/val`, via the S3-compatible API |
| Encryption | aes-256-cbc, client-side, over every file including WAL |
| WAL archiving | `archive_mode = on`, `archive_timeout = 300` — worst-case loss window five minutes |
| Schedule | Daily 03:00: full on Sunday, incremental otherwise |
| Retention | 30 daily / 12 weekly / 12 monthly, applied by the GFS selector in `run_backup.py` |

Config: `/opt/homebrew/etc/pgbackrest/pgbackrest.conf`, mode `0600`, **outside
the repository and outside the backup it protects.**

## What this covers, and what it does not

**This document is about PostgreSQL.** `01-architecture.md` §9.1 lists five
things that must survive, and only the first is protected by anything on this
page. The other four are protected by git, and the distinction matters enough
to state before anything else here.

| What | Protected by | Recovers to |
|---|---|---|
| PostgreSQL, in full | pgBackRest -> B2, everything below | Any moment inside retention |
| Governing baselines | **git -> GitHub**, private remote | Any commit |
| Persona source | **git -> GitHub** | Any commit |
| Migration history | **git -> GitHub** | Any commit |
| Repository configuration and application source | **git -> GitHub** | Any commit |
| Credentials, and the repository passphrase | **Neither, deliberately** | See below |

**GitHub is the stated off-machine protection for repository-controlled
material.** Private remote, off this machine, full history, every commit a
restore point. That is a decision, recorded rather than assumed.

**It does not replace point-in-time recovery, and nothing here should be read as
saying it does.** The two protect disjoint things. Git holds the text Val was
built from; PostgreSQL holds what she has learned, decided, spent, and been
told. Restore the repository onto a fresh machine with no database and you have
Val's character and none of her memory — every execution event, deliberation
record, and cost attribution the whole layer exists to capture is in the other
column, and none of it is reconstructible from source.

**How repository recovery is verified.** By performing it, on the same principle
as everything else here: clone the remote onto a machine that has never held the
project, build from the sequence in `docs/BUILD.md` with no undocumented step,
and confirm `docs/baselines/` and `03-persona.md` are byte-identical to the
working copy. This is the clean-clone check of WP-0.1; it is named here as the
repository's restore verification so it is not left as a build test that happens
to double as one. Last performed 14 August 2026 against a 72-file materialised
checkout.

**No secret is ever committed.** `.env` is git-ignored and `git add .env` is
refused; the B2 credentials and the repository passphrase live only in the 0600
config below and on paper. A repository backup carrying them would put every
credential wherever the repository goes.

## The key

The encryption passphrase exists in exactly two places:

1. `pgbackrest.conf` — the operative copy, which `archive_command` and the
   scheduled backup read. Local keychains cannot serve this role: the job runs
   unattended, possibly before login.
2. **Paper, held by Lord Armand**, in two physical locations. This is the only
   copy that survives the loss of the machine.

It is deliberately **not** in iCloud, not in the macOS Keychain, not in `.env`,
and not in B2. Losing both copies makes the repository permanently unreadable —
that is the property, not a defect. Demonstrated on 13 August 2026: with the
complete repository and no key (and again with a wrong key), pgBackRest cannot
read `backup.info` and restores zero files.

**The paper is verified by use.** The quarterly drill below types the passphrase
from the paper — never pasted from the config — so the copy that matters is
exercised on the same cadence as the restore.

### Accepted risk: the operative key is readable by this account

The operative passphrase sits in `pgbackrest.conf` at mode `0600`, owned by the
account PostgreSQL runs as. It has to: `archive_command` runs unattended, before
login, and cannot wait on an interactively unlocked Keychain. That decision
stands — but it carries a cost that is recorded here rather than left implied.

**Anything that can read as this operating account can read the backup
encryption key, and therefore decrypt every backup in B2.** Compromise of the
account is compromise of backup confidentiality. The separately-held paper copy
does **not** mitigate this: paper protects against *losing* the key, not against
someone *obtaining* it. The two risks are unrelated and only one is addressed.

What does limit the blast radius today:

- The B2 application key is scoped to the `valbackups` bucket, so a compromise
  reaches the backups and nothing else in the account.
- The file is `0600` and outside the git repository, so it is not exposed by a
  clone, a push, or the credential scanner's blind spots.
- Backups are encrypted at rest in B2, so B2 itself never holds plaintext.

What would actually reduce it, and is deliberately not done at Layer 0: a
separate low-privilege account for the archiver, or an HSM-backed key service
that never yields the passphrase to the filesystem. Both are Layer 3 topology
questions — they belong with the always-on box, not on a laptop.

**Status: accepted, current, and revisited at the Layer 3 migration** when the
store moves and the account model changes anyway.

## Scheduling on a laptop

Two launchd user agents, installed from `infrastructure/backup/launchd/`:

| Agent | Fires | Runs |
|---|---|---|
| `house.armand.val.backup` | daily 03:00 | `run_backup.py` — pre-flight, backup, retention, status |
| `house.armand.val.backup-watch` | hourly at :15 | `watch_backup.py` — staleness check and alerts |

Both use `StartCalendarInterval`, which per `launchd.plist(5)` **fires a missed
run on the next wake** rather than skipping it, coalescing multiple missed
firings into one. A laptop asleep at 03:00 is backed up when it opens.

**How failure surfaces**, computed from what the B2 repository actually holds
(`pgbackrest info`), not from the job's own exit status:

| Newest successful backup | Behaviour |
|---|---|
| under 26 h | silence |
| 26 h — one missed run | Notification Center banner, hourly |
| 50 h — two missed runs | modal alert that must be dismissed, hourly |

Offline is not itself an alarm: when B2 is unreachable the watcher falls back to
the status file (`/opt/homebrew/var/log/pgbackrest/val-backup-status.json`), so
working on a train does not cry wolf — but a genuinely stale backup alarms even
offline. The honest limit: a watcher on a closed laptop alerts nobody, and a
closed laptop is also writing nothing new.

## Pre-flight

`infrastructure/backup/check_b2_credential.py` runs before every scheduled
backup and can be run by hand. It asks B2's native API what the configured key
is scoped to and may do, because pgBackRest's own errors are misleading here: a
master key surfaces as 403 (reads as wrong secret; the S3 API rejects master
keys outright) and a capability-less key surfaces as 404 NoSuchBucket (reads as
wrong bucket). It requires the key to be bucket-scoped — an account-wide key in
a config file could delete the backups it exists to protect.

## Restore

Full restore to a scratch instance, then verification:

```bash
pgbackrest --config=/opt/homebrew/etc/pgbackrest/pgbackrest.conf --stanza=val --pg1-path=/path/to/scratch restore
```

Point-in-time, to any moment within retention:

```bash
pgbackrest --config=/opt/homebrew/etc/pgbackrest/pgbackrest.conf --stanza=val --pg1-path=/path/to/scratch --type=time "--target=2026-08-14 12:00:00" --target-action=promote restore
```

Start the scratch instance on port 5434 with `archive_mode = off`, then verify —
row counts per table, every foreign key, and capture-table continuity:

```bash
uv run python infrastructure/backup/verify_restore.py --source "postgresql+psycopg://localhost:5433/val" --restored "postgresql+psycopg://localhost:5434/val"
```

A restore is not complete until `verify_restore.py` exits 0. A mismatch means
the backup it came from is not trusted until the difference is explained.

## The quarterly drill

Every quarter, at minimum (`01-architecture.md` §9.3):

1. Write a scratch pgBackRest config; **type the passphrase from the paper.**
2. Restore to a scratch instance from B2 using only that config.
3. Run `verify_restore.py` against the live store. It must exit 0.
4. PITR to an arbitrary timestamp inside retention; confirm recovery stops there.
5. Destroy the scratch instance and config.

Steps 1–2 prove the paper. Step 3 proves the data. Step 4 proves the WAL chain.

## History

- **13 Aug 2026** — mechanics proven against a local encrypted repository:
  full backup, verified restore (7/7 tables, 11/11 foreign keys, capture tables
  continuous), PITR to a pre-seed timestamp, and the no-key/wrong-key failure
  cases.
- **14 Aug 2026** — first real backup to B2: 42.2 MB database, 4.7 MB encrypted
  in the bucket. WAL archiving enabled. Both agents installed and loaded.
- **16 Aug 2026** — first unattended scheduled run: 03:15, a Sunday, correctly a
  full backup.
- **17 Aug 2026, 03:08** — **second consecutive unattended scheduled run**, a
  Monday, correctly an incremental. With this, WP-0.3's "confirmed by observing
  two consecutive days" is **satisfied**: two scheduled runs on consecutive
  days, both with no human step, and the full/incremental selection correct on
  both. Verified from `pgbackrest info` against B2, not from the agent's own
  log.
- **17 Aug 2026, 09:58** — an on-demand **incremental** backup taken before
  applying migration `0003`, per §9.2's "on demand before any schema migration".
  Chained onto 16 August's full, so it is a complete restore point for the
  pre-migration schema. Backup scope beyond PostgreSQL clarified above.

**WP-0.3 nonetheless remains BLOCKED**, on one criterion only: **a restore
pulled back from B2 has still not been performed.** Every restore proved so far
— 13 August's full restore, PITR, and both key-failure cases — used a *local*
repository. Restoring from the local copy proves the encryption, the catalogue,
and the data; it does not prove that the bytes in Backblaze are retrievable and
sound. That is the one thing an off-machine backup exists to establish, and
until it is done the package does not pass (`00-charter.md` invariant 35).
