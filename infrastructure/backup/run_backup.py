"""The scheduled backup: pre-flight, backup, GFS retention, status, alert.

Run daily at 03:00 by the launchd agent `house.armand.val.backup`. launchd's
StartCalendarInterval fires a missed run on the next wake, so a laptop asleep at
03:00 is backed up when it opens; multiple missed firings coalesce into one run,
which for a backup is correct — current state, not replays.

Order of operations, each failing loudly rather than proceeding:

1. **Pre-flight** — the credential is asked what it can do (check_b2_credential)
   before anything depends on it.
2. **Backup** — full on Sunday, incremental otherwise. pgBackRest promotes an
   incremental to full on its own when no full exists.
3. **Retention** — 30 daily / 12 weekly / 12 monthly (01-architecture.md §9),
   applied as a keep-list over full backup sets with `expire --set` for the
   rest. pgBackRest's own retention is configured far wider (370 days), so this
   selector can only ever be the stricter of the two.
4. **Status** — a JSON file the watcher reads, recording attempt and outcome.
5. **Alert** — a Notification Center banner on failure. Success is silent.

Stdlib only: this runs unattended and must not depend on the project's
virtualenv being healthy.
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path

from check_b2_credential import main as preflight

PGBACKREST = "/opt/homebrew/bin/pgbackrest"
CONFIG = "/opt/homebrew/etc/pgbackrest/pgbackrest.conf"
STANZA = "val"
STATUS_FILE = Path("/opt/homebrew/var/log/pgbackrest/val-backup-status.json")
OSASCRIPT = "/usr/bin/osascript"

KEEP_DAILY_DAYS = 30
KEEP_WEEKLY = 12
KEEP_MONTHLY = 12
SUNDAY = 6


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [PGBACKREST, f"--config={CONFIG}", f"--stanza={STANZA}", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=3600,
    )


def notify(message: str) -> None:
    """Notification Center banner. Never raises — alerting must not mask the error."""
    script = f'display notification "{message}" with title "Val backup" sound name "Basso"'
    try:
        subprocess.run([OSASCRIPT, "-e", script], check=False, timeout=30)  # noqa: S603
    except OSError:
        pass


def read_status() -> dict[str, object]:
    """The status file, or an empty record if it does not exist yet."""
    try:
        loaded = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except OSError, ValueError:
        return {}


def write_status(**fields: object) -> None:
    """Merge fields into the status file."""
    status = read_status()
    status.update(fields)
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def full_backups() -> list[tuple[str, datetime.datetime]]:
    """Full backup sets in the repository: (label, stop time), oldest first."""
    result = _run("info", "--output=json")
    if result.returncode != 0:
        raise RuntimeError(f"pgbackrest info failed: {result.stderr.strip()[:300]}")
    stanzas = json.loads(result.stdout)
    sets: list[tuple[str, datetime.datetime]] = []
    for backup in stanzas[0].get("backup", []):
        if backup.get("type") == "full":
            stop = datetime.datetime.fromtimestamp(backup["timestamp"]["stop"], tz=datetime.UTC)
            sets.append((backup["label"], stop))
    sets.sort(key=lambda item: item[1])
    return sets


def keep_labels(fulls: list[tuple[str, datetime.datetime]], now: datetime.datetime) -> set[str]:
    """The GFS keep-list: 30 days of everything, 12 weeklies, 12 monthlies.

    Weekly keeps one full per ISO week; monthly keeps the first full of each
    calendar month. A full inside the 30-day window is kept regardless.
    """
    keep: set[str] = set()

    for label, stop in fulls:
        if (now - stop).days <= KEEP_DAILY_DAYS:
            keep.add(label)

    by_week: dict[tuple[int, int], str] = {}
    for label, stop in fulls:
        year, week, _ = stop.isocalendar()
        by_week.setdefault((year, week), label)
    keep.update(label for _, label in sorted(by_week.items())[-KEEP_WEEKLY:])

    by_month: dict[tuple[int, int], str] = {}
    for label, stop in fulls:
        by_month.setdefault((stop.year, stop.month), label)
    keep.update(label for _, label in sorted(by_month.items())[-KEEP_MONTHLY:])

    return keep


def apply_retention(now: datetime.datetime) -> list[str]:
    """Expire full sets outside the keep-list. Returns the labels expired."""
    fulls = full_backups()
    keep = keep_labels(fulls, now)
    expired: list[str] = []
    for label, _ in fulls:
        if label in keep:
            continue
        result = _run("expire", f"--set={label}")
        if result.returncode != 0:
            raise RuntimeError(f"expire --set={label} failed: {result.stderr.strip()[:300]}")
        expired.append(label)
    return expired


def main() -> int:
    """One scheduled backup run."""
    now = datetime.datetime.now(datetime.UTC)
    write_status(last_attempt=now.isoformat())

    if preflight() != 0:
        write_status(last_error=f"{now.isoformat()}: credential pre-flight failed")
        notify("Backup NOT run: the B2 credential failed pre-flight.")
        return 1

    backup_type = "full" if now.astimezone().weekday() == SUNDAY else "incr"
    result = _run("backup", f"--type={backup_type}")
    if result.returncode != 0:
        error = result.stderr.strip().splitlines()[-1][:300] if result.stderr else "?"
        write_status(last_error=f"{now.isoformat()}: backup failed: {error}")
        notify("Backup FAILED. See val-backup-status.json.")
        return 1

    try:
        expired = apply_retention(now)
    except RuntimeError as error:
        # The backup itself succeeded; retention failing is a warning, loudly.
        write_status(last_error=f"{now.isoformat()}: retention: {error}")
        notify("Backup succeeded but retention failed. See val-backup-status.json.")
        write_status(last_success=now.isoformat(), last_type=backup_type)
        return 1

    write_status(
        last_success=now.isoformat(),
        last_type=backup_type,
        last_expired=expired,
        last_error=None,
    )
    print(f"backup ok: type={backup_type}, expired={expired or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
