"""The watcher: notices a backup that has not succeeded, without being asked.

Run hourly by the launchd agent `house.armand.val.backup-watch`. It computes the
age of the newest successful backup and escalates:

| Age of newest success | Behaviour |
|---|---|
| under 26 hours | silence |
| 26 hours (one missed run) | Notification Center banner, re-issued hourly |
| 50 hours (two missed runs) | modal alert that must be dismissed, hourly |

It deliberately does not trust the backup job's own exit status alone: the
authoritative answer is `pgbackrest info` — what the repository on B2 actually
holds. A job that died before reporting, a laptop that slept through three runs,
and a repository that stopped accepting writes all surface here identically, as
staleness. When B2 is unreachable (offline, wrong network), the status file's
last recorded success stands in, so being offline does not itself trip a false
alarm — but a genuinely stale backup still alarms even offline.

Only runs while the machine is awake, which is the honest limit of a laptop
watcher: a closed laptop alerts nobody, but it is also writing nothing new.
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path

PGBACKREST = "/opt/homebrew/bin/pgbackrest"
CONFIG = "/opt/homebrew/etc/pgbackrest/pgbackrest.conf"
STANZA = "val"
STATUS_FILE = Path("/opt/homebrew/var/log/pgbackrest/val-backup-status.json")
OSASCRIPT = "/usr/bin/osascript"

BANNER_HOURS = 26
MODAL_HOURS = 50


def newest_success_from_repository() -> datetime.datetime | None:
    """Stop time of the newest backup B2 actually holds, or None if unreachable."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [PGBACKREST, f"--config={CONFIG}", f"--stanza={STANZA}", "info", "--output=json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            return None
        backups = json.loads(result.stdout)[0].get("backup", [])
        if not backups:
            return None
        newest = max(backup["timestamp"]["stop"] for backup in backups)
        return datetime.datetime.fromtimestamp(newest, tz=datetime.UTC)
    except OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired:
        return None


def newest_success_from_status() -> datetime.datetime | None:
    """Fallback when B2 is unreachable: the last success the runner recorded."""
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        recorded = status.get("last_success")
        if isinstance(recorded, str):
            return datetime.datetime.fromisoformat(recorded)
    except OSError, ValueError:
        pass
    return None


def alert(message: str, modal: bool) -> None:
    """A banner, or at two missed runs a dialog that must be dismissed."""
    if modal:
        script = f'display alert "Val backup is failing" message "{message}" as critical'
    else:
        script = f'display notification "{message}" with title "Val backup" sound name "Basso"'
    try:
        subprocess.run([OSASCRIPT, "-e", script], check=False, timeout=300)  # noqa: S603
    except OSError, subprocess.TimeoutExpired:
        pass


def main() -> int:
    """One watcher pass."""
    now = datetime.datetime.now(datetime.UTC)
    newest = newest_success_from_repository()
    source = "repository"
    if newest is None:
        newest = newest_success_from_status()
        source = "status file (B2 unreachable)"

    if newest is None:
        alert("No successful backup has ever been recorded.", modal=True)
        print("watcher: no success recorded anywhere — modal raised")
        return 1

    age_hours = (now - newest).total_seconds() / 3600
    print(f"watcher: newest success {age_hours:.1f}h ago, per {source}")

    if age_hours >= MODAL_HOURS:
        alert(
            f"Newest successful backup is {age_hours:.0f} hours old — "
            "two scheduled runs have not succeeded.",
            modal=True,
        )
        return 1
    if age_hours >= BANNER_HOURS:
        alert(f"Newest successful backup is {age_hours:.0f} hours old.", modal=False)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
