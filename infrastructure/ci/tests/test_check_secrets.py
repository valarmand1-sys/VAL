"""Tests for the credential scanner.

Every fake credential here is assembled at runtime from harmless fragments, so
that this file does not itself contain a credential-shaped literal and does not
have to be excluded from the scan it exercises.
"""

from pathlib import Path

import pytest

import check_secrets

DECLARED = check_secrets.secret_variable_names()


def fake(*fragments: str) -> str:
    """Build a credential-shaped string without writing one down."""
    return "".join(fragments)


# --- what must be caught ------------------------------------------------------


def test_a_private_key_block_is_caught() -> None:
    """Never a false positive, and never acceptable."""
    line = fake("-----BE", "GIN RSA PRIVATE KE", "Y-----")
    assert check_secrets.scan_line(line, DECLARED) == "a private key block"


def test_a_value_against_a_declared_secret_variable_is_caught() -> None:
    """The specific failure: a real credential for a variable this project uses.

    The declared list is supplied here rather than read from `.env.example`, so
    this holds whatever that file happens to contain today. Which variables are
    declared changes as work packages land; that the rule fires does not.
    """
    declared = ["VAL_ANTHROPIC_API_KEY"]
    line = f"{declared[0]}={fake('sk-', 'ant-', 'a1b2c3d4e5f6g7h8i9j0k1')}"
    assert check_secrets.scan_line(line, declared) == f"a value assigned to {declared[0]}"


def test_a_key_id_is_treated_as_half_a_credential() -> None:
    """An identifier that pairs with a secret is itself secret-shaped."""
    assert check_secrets.secret_variable_names() is not None
    line = "SOME_KEY_ID=" + fake("00", "4abcdef0123456", "789abcd")
    assert check_secrets.scan_line(line, []) is not None


@pytest.mark.parametrize(
    "line",
    [
        "password = " + fake("hunter", "2hunter2hunter2"),
        'api_key: "' + fake("abcdef", "1234567890") + '"',
        "CLIENT_SECRET=" + fake("s3cr3t", "s3cr3ts3cr3t"),
    ],
)
def test_a_secret_shaped_assignment_is_caught(line: str) -> None:
    """A secret-shaped name with a literal value, whatever the variable is called."""
    assert check_secrets.scan_line(line, DECLARED) is not None


def test_a_url_carrying_a_password_is_caught() -> None:
    """The way a credential most often reaches a committed file."""
    line = "postgresql://val:" + fake("s3cr", "etpass") + "@localhost:5433/val"
    assert check_secrets.scan_line(line, DECLARED) == "a URL carrying an inline password"


def test_a_provider_issued_key_is_caught() -> None:
    """Recognisable formats are caught regardless of the variable name."""
    line = "value = " + fake("AK", "IA") + "ABCDEFGHIJKLMNOP"
    assert check_secrets.scan_line(line, DECLARED) == "a provider-issued key"


# --- what must not be caught --------------------------------------------------
#
# A scanner that cries wolf gets disabled, which is worse than not having one.


@pytest.mark.parametrize(
    "line",
    [
        "VAL_ANTHROPIC_API_KEY=",
        "VAL_BACKUP_ALERT_EMAIL=",
        'password = os.environ["VAL_PASSWORD"]',
        "api_key = read_key_from_keychain()",
        "POSTGRES_PASSWORD: ${{ secrets.PGPASSWORD }}",
        "# the application key is stored in .env, never here",
        "token = None",
        "VAL_DATABASE_URL=postgresql+psycopg://localhost:5433/val",
        "secret: <fill this in>",
    ],
)
def test_references_and_empty_values_are_not_credentials(line: str) -> None:
    """References, templates, calls, prose, and empty values all pass."""
    assert check_secrets.scan_line(line, DECLARED) is None


def test_env_example_is_committable_and_valueless() -> None:
    """The register of secret variables is committed, and holds no value."""
    example = Path(check_secrets.REPO_ROOT) / ".env.example"
    assert example.is_file()
    for name in check_secrets.secret_variable_names():
        for line in example.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                assert line.strip() == f"{name}=", f"{name} carries a value in .env.example"


def test_the_committable_tree_is_clean() -> None:
    """The tree passes the check it ships with."""
    assert check_secrets.scan(check_secrets.committable_files()) == []
