"""Pre-flight check on the B2 credential, before anything tries to back up.

pgBackRest reports a credential problem as whatever the storage API returned,
which for Backblaze is misleading in two specific ways:

  - A master application key is rejected with **403**. B2's S3-compatible API
    does not accept master keys at all, which reads like a wrong secret.
  - A key with no capabilities is rejected with **404 NoSuchBucket**, which reads
    like a wrong bucket name and sends you looking in the wrong place.

Both cost a round trip to diagnose. This asks B2 directly what the key is scoped
to and what it may do, so the answer is the actual answer.

It reads the credential from pgbackrest.conf and prints none of it — only the
bucket scope, the capabilities, and the endpoint, all of which are non-secret.

Exit code 0 means the credential can run a backup. Exit code 1 means it cannot,
and says why.
"""

import base64
import json
import pathlib
import sys
import urllib.error
import urllib.request

CONFIG = pathlib.Path("/opt/homebrew/etc/pgbackrest/pgbackrest.conf")
AUTHORIZE_URL = "https://api.backblazeb2.com/b2api/v3/b2_authorize_account"

#: What pgBackRest needs: read and list to restore and check, write to back up,
#: delete to expire. Anything less and the failure surfaces mid-operation.
REQUIRED_CAPABILITIES = frozenset({"listFiles", "readFiles", "writeFiles", "deleteFiles"})

MASTER_KEY_ID_LENGTH = 12


def read_config() -> dict[str, str]:
    """Read pgbackrest.conf into a mapping."""
    values: dict[str, str] = {}
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values


def main() -> int:
    """Report what the configured B2 key is scoped to and may do."""
    config = read_config()
    key_id = config.get("repo1-s3-key", "")
    secret = config.get("repo1-s3-key-secret", "")
    bucket = config.get("repo1-s3-bucket", "")

    if not key_id or not secret:
        print("repo1-s3-key or repo1-s3-key-secret is blank.", file=sys.stderr)
        return 1

    if len(key_id) == MASTER_KEY_ID_LENGTH:
        print(
            f"repo1-s3-key is {MASTER_KEY_ID_LENGTH} characters, which is a B2 master "
            "application key. The S3-compatible API rejects master keys with 403. "
            "Create an application key in the B2 console instead.",
            file=sys.stderr,
        )
        return 1

    token = base64.b64encode(f"{key_id}:{secret}".encode()).decode()
    request = urllib.request.Request(AUTHORIZE_URL, headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        print(f"B2 rejected the credential: HTTP {error.code}", file=sys.stderr)
        return 1

    allowed = payload.get("allowed", {})
    scope = allowed.get("bucketName")
    capabilities = set(allowed.get("capabilities", []))

    print(f"bucket scope : {scope or 'all buckets'}")
    print(f"capabilities : {', '.join(sorted(capabilities)) or '(none)'}")
    print(f"endpoint     : {payload.get('apiInfo', {}).get('storageApi', {}).get('s3ApiUrl', '?')}")

    problems: list[str] = []
    missing = REQUIRED_CAPABILITIES - capabilities
    if missing:
        problems.append(
            f"the key is missing {', '.join(sorted(missing))}. In the B2 console this is "
            "the 'Type of Access' field — it must be Read and Write."
        )
    if scope is not None and scope != bucket:
        problems.append(f"the key is scoped to {scope!r}, but the repository is {bucket!r}.")
    if scope is None:
        problems.append(
            f"the key is not restricted to a bucket. Scope it to {bucket!r} so that this "
            "file cannot reach anything else in the account."
        )

    if problems:
        print("\nThis credential cannot run a backup:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"\nCredential is usable: scoped to {bucket}, with read, write, list, and delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
