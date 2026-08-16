"""Fail if anything credential-shaped has entered the committable tree.

Nothing in this repository may contain a credential (`00-charter.md` §6). The
`.gitignore` keeps `.env` out, but an ignore rule only protects the file it names.
This checks the thing that actually matters: that no value which looks like a
secret appears in any file git would carry.

**Scope is git's own view of the tree** — tracked files plus untracked files that
are not ignored. That is precisely the set a commit could contain. `.env` is
ignored and therefore never read here, which is deliberate: once it holds real
credentials, a checker that opened it would be the leak.

The detections, in order of how much they mean:

1. A private key block. Never a false positive.
2. A value assigned to one of the secret variables `.env.example` declares.
   These are the credentials this project actually handles, so a value against
   one of those names in a committed file is the specific failure to prevent.
3. A value assigned to a secret-shaped name of any kind.
4. A URL carrying an inline password.
5. A provider-issued key in a recognisable format.

Exit code 0 means clean. Exit code 1 means at least one credential-shaped literal
remains.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
GIT = "/usr/bin/git"

BINARY_SUFFIXES = frozenset(
    {".icns", ".ico", ".jpeg", ".jpg", ".lock", ".pdf", ".png", ".webp", ".woff", ".woff2"}
)

# Assembled from fragments so this file does not itself contain the literals it
# hunts for, and so `ruff format` cannot reassemble them.


def _token(*fragments: str) -> str:
    """Assemble a pattern fragment out of pieces that are harmless apart."""
    return "".join(fragments)


PEM_BLOCK = re.compile(_token("-----BE", "GIN [A-Z ]*PRIVATE KE", "Y-----"))

#: Names that mean a secret, wherever they appear.
SENSITIVE_NAME = (
    r"(?:pass(?:word|wd)?|secret|token|credential|"
    r"api[_-]?key|access[_-]?key|application[_-]?key|client[_-]?secret|"
    r"cipher[_-]?pass|private[_-]?key|key[_-]?id)"
)

#: A value that is a reference, a template, or plainly empty is not a secret.
NOT_A_VALUE = re.compile(
    r"^\s*$"
    r"|^[\"']{0,2}\s*$"
    r"|^\$"  # a shell variable, a CI context expression, a substitution
    r"|^[<{]"  # <fill this in>, {placeholder}
    r"|^(?:os\.environ|os\.getenv|getenv|environ|process\.env|std::env)"
    r"|^(?:None|null|nil|true|false|yes|no)$"
    r"|^-+$"
    # A value containing a call is an expression, not a literal. Without this,
    # `password = read_password()` reads as a leak and real code cannot pass.
    r"|.*\("
)

SECRET_ASSIGNMENT = re.compile(
    r"(" + SENSITIVE_NAME + r")[\"']?\s*[:=]\s*([\"']?)([^\s\"',;)]{6,})",
    re.IGNORECASE,
)


def _is_forwarded(name: str, quote: str, value: str) -> bool:
    """Whether this is a variable being passed rather than a secret written down.

    The narrow, safe case only: an **unquoted** value whose text equals the name
    it is assigned to — forwarding a key argument into an SDK client constructor,
    the commonest shape in this repository. Anything else unquoted is still
    flagged, so a real secret sitting unquoted in a `.env`-style file is caught.
    """
    if quote:
        return False
    normalise = re.compile(r"[^a-z0-9]")
    return normalise.sub("", name.lower()) == normalise.sub("", value.lower())


URL_INLINE_AUTH = re.compile(r"://[^/\s:@]+:([^/\s:@]{3,})@")

PROVIDER_KEY = re.compile(
    _token("AK", "IA") + r"[0-9A-Z]{16}"
    r"|" + _token("AS", "IA") + r"[0-9A-Z]{16}"
    r"|" + _token("sk-", "ant-") + r"[0-9A-Za-z_-]{20,}"
    r"|" + _token("gh", "p_") + r"[0-9A-Za-z]{36}"
)


def secret_variable_names() -> list[str]:
    """Secret-bearing variable names declared in `.env.example`.

    `.env.example` is the register of what this project handles. A name in it
    whose own text is secret-shaped must never appear with a value anywhere.
    """
    if not ENV_EXAMPLE.is_file():
        return []
    names: list[str] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name = stripped.split("=", 1)[0].strip()
        if re.search(SENSITIVE_NAME, name, re.IGNORECASE):
            names.append(name)
    return names


def committable_files() -> list[Path]:
    """Every file git would carry: tracked, plus untracked and not ignored."""
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, no input
        [GIT, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    paths: list[Path] = []
    for entry in result.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        path = REPO_ROOT / entry
        if path.is_file() and path.suffix not in BINARY_SUFFIXES:
            paths.append(path)
    return paths


def scan_line(line: str, declared: list[str]) -> str | None:
    """Return a description of the credential on this line, if there is one."""
    if PEM_BLOCK.search(line):
        return "a private key block"

    for name in declared:
        match = re.search(rf"{re.escape(name)}\s*[:=]\s*[\"']?([^\s\"',;)]+)", line)
        if match is not None and NOT_A_VALUE.match(match.group(1)) is None:
            return f"a value assigned to {name}"

    match = SECRET_ASSIGNMENT.search(line)
    if match is not None:
        name, quote, value = match.group(1), match.group(2), match.group(3)
        if NOT_A_VALUE.match(value) is None and not _is_forwarded(name, quote, value):
            return "a value assigned to a secret-shaped name"

    match = URL_INLINE_AUTH.search(line)
    if match is not None and NOT_A_VALUE.match(match.group(1)) is None:
        return "a URL carrying an inline password"

    if PROVIDER_KEY.search(line):
        return "a provider-issued key"

    return None


def scan(paths: list[Path]) -> list[str]:
    """Scan every file for credential-shaped literals."""
    declared = secret_variable_names()
    findings: list[str] = []
    for path in paths:
        relative = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError, OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            finding = scan_line(line, declared)
            if finding is not None:
                findings.append(f"{relative}:{number}: {finding}")
    return findings


def main() -> int:
    """Run the scan and report."""
    paths = committable_files()
    findings = scan(paths)

    if findings:
        print(
            f"{len(findings)} credential-shaped literal(s) in the committable tree "
            "(00-charter.md §6):",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\nCredentials belong in .env, which is ignored, and are read from the "
            "environment at startup. Never in a committed file.",
            file=sys.stderr,
        )
        return 1

    declared = secret_variable_names()
    print(
        f"No credential-shaped literal across {len(paths)} committable files "
        f"({len(declared)} secret variables declared in .env.example, all valueless)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
