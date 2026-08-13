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
    """The specific failure: a real credential for a variable this project uses."""
    assert DECLARED, ".env.example declares no secret variables"
    line = f"{DECLARED[0]}={fake('K0', '0abc123def456', '789ghi')}"
    assert check_secrets.scan_line(line, DECLARED) == f"a value assigned to {DECLARED[0]}"


def test_both_halves_of_the_b2_key_pair_are_declared_secret() -> None:
    """A key id is half a credential, and is treated as one."""
    assert "VAL_B2_KEY_ID" in DECLARED
    assert "VAL_B2_APPLICATION_KEY" in DECLARED


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
        "VAL_B2_APPLICATION_KEY=",
        "VAL_B2_KEY_ID=",
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
    for name in DECLARED:
        for line in example.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                assert line.strip() == f"{name}=", f"{name} carries a value in .env.example"


def test_the_committable_tree_is_clean() -> None:
    """The tree passes the check it ships with."""
    assert check_secrets.scan(check_secrets.committable_files()) == []
