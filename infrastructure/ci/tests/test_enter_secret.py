"""The local-only credential entry tool: it edits exactly what it names and refuses the rest.

Every value here is an obvious stand-in assembled at run time; no credential-shaped
literal appears in this file.
"""

import plistlib
import stat
from pathlib import Path

import enter_secret
import pytest
from enter_secret import (
    EntryRefusedError,
    acceptable,
    refuse_unsafe_context,
    replace_conf_values,
    replace_env_values,
    replace_plist_values,
    write_private,
)

OLD = "old" + "-stand-in"
NEW = "new" + "\\1-stand-in$&"  # regex-hostile on purpose: it must land verbatim

CONF = (
    f"[global]\nrepo1-type=s3\nrepo1-s3-key={OLD}\nrepo1-s3-key-secret={OLD}\n"
    "repo1-path=/val\n[val]\npg1-port=5433\n"
)


def test_conf_replaces_only_the_named_lines_and_lands_verbatim() -> None:
    out = replace_conf_values(CONF, {"repo1-s3-key": NEW})
    assert f"repo1-s3-key={NEW}\n" in out
    assert f"repo1-s3-key-secret={OLD}\n" in out, "the longer key sharing a prefix is untouched"
    assert out.replace(f"repo1-s3-key={NEW}", f"repo1-s3-key={OLD}") == CONF


def test_conf_refuses_a_missing_or_repeated_key() -> None:
    with pytest.raises(EntryRefusedError):
        replace_conf_values(CONF, {"repo2-s3-key": NEW})
    with pytest.raises(EntryRefusedError):
        replace_conf_values(CONF + f"repo1-s3-key={OLD}\n", {"repo1-s3-key": NEW})


def test_env_replaces_only_the_named_line() -> None:
    text = f"# note\nVAL_A={OLD}\nVAL_A_LONGER={OLD}\nVAL_B=plain\n"
    out = replace_env_values(text, {"VAL_A": NEW})
    assert out == f"# note\nVAL_A={NEW}\nVAL_A_LONGER={OLD}\nVAL_B=plain\n"
    with pytest.raises(EntryRefusedError):
        replace_env_values(text, {"VAL_MISSING": NEW})


def test_plist_sets_a_declared_variable_and_nothing_else() -> None:
    before = {
        "Label": "x",
        "EnvironmentVariables": {"VAL_A": OLD, "VAL_B": "plain"},
        "KeepAlive": True,
    }
    after = plistlib.loads(replace_plist_values(plistlib.dumps(before), {"VAL_A": NEW}))
    assert after == {**before, "EnvironmentVariables": {"VAL_A": NEW, "VAL_B": "plain"}}
    with pytest.raises(EntryRefusedError):
        replace_plist_values(plistlib.dumps(before), {"VAL_UNDECLARED": NEW})


def test_a_credential_is_one_unbroken_printable_token() -> None:
    assert acceptable("abc-123_XYZ")
    for bad in ("", "two words", "line\nbreak", "tab\there"):
        assert not acceptable(bad)


def test_write_private_is_owner_only_and_leaves_no_second_copy(tmp_path: Path) -> None:
    target = tmp_path / "conf"
    target.write_text("before")
    target.chmod(0o644)
    write_private(target, b"after")
    assert target.read_bytes() == b"after"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["conf"]


def test_it_refuses_an_assistant_shell_and_a_missing_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(EntryRefusedError, match="assistant"):
        refuse_unsafe_context()
    for marker in enter_secret.ASSISTANT_MARKERS:
        monkeypatch.delenv(marker, raising=False)
    with pytest.raises(EntryRefusedError, match="terminal"):  # pytest's stdin is not a TTY
        refuse_unsafe_context()


def test_the_targets_write_only_to_the_established_destinations() -> None:
    assert sorted(enter_secret.TARGETS) == ["anthropic", "backblaze", "lmstudio", "openai"]
    names = {f.env_name for fields in enter_secret.TARGETS.values() for f in fields if f.env_name}
    assert names >= enter_secret.ALSO_IN_DOTENV
    assert "VAL_LMSTUDIO_API_TOKEN" not in enter_secret.ALSO_IN_DOTENV, ".env never held it"
