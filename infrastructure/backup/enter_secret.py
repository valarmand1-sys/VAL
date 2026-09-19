"""Local-only entry of a replacement credential. Run by the owner, in Terminal, by hand.

Owner authorisation, 19 September 2026 (credential security, phase two). A new
credential must reach its owner-only destination without passing through an
assistant session, a shell history, a log, a terminal echo or a second copy.

    ~/.local/bin/uv run --no-project python infrastructure/backup/enter_secret.py TARGET

The command line names a target and nothing else, so the shell history records
no secret. Each value is asked for twice with echo off and compared. It is
written only to the established destination, atomically, at mode 0600. Nothing
is printed, logged or kept anywhere else. The tool refuses to run inside an
assistant session or without a real terminal.

Targets and the only places each one writes:

- `backblaze`  — `repo1-s3-key` and `repo1-s3-key-secret` in pgbackrest.conf
- `openai`     — `VAL_OPENAI_API_KEY` in the API launch agent and the repository `.env`
- `anthropic`  — `VAL_ANTHROPIC_API_KEY` in the same two places
- `lmstudio`   — `VAL_LMSTUDIO_API_TOKEN` in the API launch agent

Stdlib only, like the rest of this directory: it must not depend on the
project's virtualenv being healthy.
"""

import getpass
import os
import plistlib
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PGBACKREST_CONF = Path("/opt/homebrew/etc/pgbackrest/pgbackrest.conf")
API_PLIST = Path.home() / "Library/LaunchAgents/house.armand.val.api.plist"
DOTENV = REPO_ROOT / ".env"

#: Present in every assistant-driven shell. A credential typed there is a
#: credential the assistant's tooling could observe.
ASSISTANT_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID")


class EntryRefusedError(Exception):
    """The tool will not proceed; the message never contains a secret."""


@dataclass(frozen=True)
class Field:
    prompt: str
    conf_key: str | None = None
    env_name: str | None = None


TARGETS: dict[str, tuple[Field, ...]] = {
    "backblaze": (
        Field("Backblaze keyID", conf_key="repo1-s3-key"),
        Field("Backblaze applicationKey", conf_key="repo1-s3-key-secret"),
    ),
    "openai": (Field("OpenAI API key", env_name="VAL_OPENAI_API_KEY"),),
    "anthropic": (Field("Anthropic API key", env_name="VAL_ANTHROPIC_API_KEY"),),
    "lmstudio": (Field("LM Studio API token", env_name="VAL_LMSTUDIO_API_TOKEN"),),
}

#: Targets whose variable also lives in the repository `.env`.
ALSO_IN_DOTENV = frozenset({"VAL_OPENAI_API_KEY", "VAL_ANTHROPIC_API_KEY"})


# --- pure text edits (tested) ------------------------------------------------------------


def _set_line(pattern: re.Pattern[str], value: str, text: str) -> str:
    """Substitute by function, so the value lands verbatim whatever characters it holds."""

    def replacement(match: re.Match[str]) -> str:
        return match.group("head") + value

    return pattern.sub(replacement, text)


def replace_conf_values(text: str, values: dict[str, str]) -> str:
    """Replace `key=value` lines in a pgBackRest INI; every key must exist exactly once."""
    for key, value in values.items():
        pattern = re.compile(rf"^(?P<head>[ \t]*{re.escape(key)}[ \t]*=)[^\n]*$", re.MULTILINE)
        if len(pattern.findall(text)) != 1:
            raise EntryRefusedError(f"pgbackrest.conf does not hold exactly one `{key}` line")
        text = _set_line(pattern, value, text)
    return text


def replace_env_values(text: str, values: dict[str, str]) -> str:
    """Replace `NAME=value` lines in a dotenv file; every name must exist exactly once."""
    for name, value in values.items():
        pattern = re.compile(rf"^(?P<head>{re.escape(name)}=)[^\n]*$", re.MULTILINE)
        if len(pattern.findall(text)) != 1:
            raise EntryRefusedError(f".env does not hold exactly one `{name}` line")
        text = _set_line(pattern, value, text)
    return text


def replace_plist_values(data: bytes, values: dict[str, str]) -> bytes:
    """Set launch-agent environment variables; each must already be declared there."""
    document = plistlib.loads(data)
    environment = document.get("EnvironmentVariables")
    if not isinstance(environment, dict):
        raise EntryRefusedError("the launch agent declares no EnvironmentVariables")
    for name, value in values.items():
        if name not in environment:
            raise EntryRefusedError(f"the launch agent does not declare `{name}`")
        environment[name] = value
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=False)


def acceptable(value: str) -> bool:
    """A credential is one unbroken printable token."""
    return bool(value) and not re.search(r"\s", value) and value.isprintable()


# --- effects -------------------------------------------------------------------------------


def write_private(path: Path, data: bytes) -> None:
    """Replace `path` atomically with `data`, owner read/write only, no second copy left."""
    descriptor, temporary = tempfile.mkstemp(prefix=".entry-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    path.chmod(0o600)


def ask(prompt: str) -> str:
    for _ in range(3):
        first = getpass.getpass(f"{prompt} (hidden): ").strip()
        second = getpass.getpass(f"{prompt} again (hidden): ").strip()
        if first != second:
            print("The two entries differ. Nothing was written. Try again.")
            continue
        if not acceptable(first):
            print("That is empty or contains a space or line break. Nothing was written.")
            continue
        return first
    raise EntryRefusedError("three attempts did not produce a usable value")


def refuse_unsafe_context() -> None:
    if any(marker in os.environ for marker in ASSISTANT_MARKERS):
        raise EntryRefusedError(
            "this shell belongs to an assistant session. Open Terminal.app and run it there."
        )
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise EntryRefusedError("no real terminal: the value would not be hidden. Run it by hand.")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in TARGETS:
        print(
            "usage: enter_secret.py TARGET, where TARGET is one of: " + ", ".join(sorted(TARGETS))
        )
        return 2
    try:
        refuse_unsafe_context()
        fields = TARGETS[argv[1]]
        conf_values: dict[str, str] = {}
        env_values: dict[str, str] = {}
        for field in fields:
            value = ask(field.prompt)
            if field.conf_key is not None:
                conf_values[field.conf_key] = value
            if field.env_name is not None:
                env_values[field.env_name] = value
        written: list[Path] = []
        if conf_values:
            text = replace_conf_values(PGBACKREST_CONF.read_text(), conf_values)
            write_private(PGBACKREST_CONF, text.encode())
            written.append(PGBACKREST_CONF)
        if env_values:
            write_private(API_PLIST, replace_plist_values(API_PLIST.read_bytes(), env_values))
            written.append(API_PLIST)
            for_dotenv = {k: v for k, v in env_values.items() if k in ALSO_IN_DOTENV}
            if for_dotenv:
                write_private(DOTENV, replace_env_values(DOTENV.read_text(), for_dotenv).encode())
                written.append(DOTENV)
    except EntryRefusedError as refused:
        print(f"Refused: {refused}")
        return 1
    print("Written, owner-only, nothing displayed:")
    for path in written:
        print(f"  {path}")
    print("Reply to the assistant with the single word: entered")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
