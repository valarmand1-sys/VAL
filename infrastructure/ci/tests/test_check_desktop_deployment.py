"""The deployment check fails on the shape that actually failed — and only then.

The owner acceptance failure of 21 September 2026 was not a rendering defect. A
build that demonstrably renders the persisted image was installed, and macOS
launched a different copy of the same application instead, because four earlier
builds sat beside it in `/Applications` carrying the same identifier. The copy it
chose was old enough that its content security policy refused the governed byte
origin, so no request was ever made.

These exercise that shape directly, including the failure branches: a check that
has never been seen red is an assertion, not a control.
"""

from __future__ import annotations

from pathlib import Path

from check_desktop_deployment import IDENTIFIER, Bundle, bundles_in, problems_with

OTHER = "com.example.something-else"


def bundle(name: str, identifier: str = IDENTIFIER, digest: str | None = "a" * 64) -> Bundle:
    return Bundle(path=Path("/Applications") / name, identifier=identifier, binary_sha256=digest)


def test_one_installed_bundle_is_the_whole_requirement() -> None:
    assert problems_with([bundle("Val.app")]) == []


def test_nothing_installed_is_not_a_failure() -> None:
    # A machine that has never installed the desktop is not misconfigured.
    assert problems_with([]) == []
    assert problems_with([bundle("Something.app", identifier=OTHER)]) == []


def test_the_real_failure_two_bundles_claiming_one_identifier() -> None:
    problems = problems_with([bundle("Val.app"), bundle("Val (built 2026-09-13).app")])
    assert len(problems) == 1
    assert "2 application bundles" in problems[0]
    # The message names both, because the reader has to go and move one.
    assert "/Applications/Val.app" in problems[0]
    assert "/Applications/Val (built 2026-09-13).app" in problems[0]


def test_the_exact_situation_found_on_the_machine() -> None:
    # Five bundles, one identifier, which is what `open -b` resolved arbitrarily.
    installed = [
        bundle("Val.app"),
        bundle("Val (built 2026-09-13).app"),
        bundle("Val (built 2026-09-14).app"),
        bundle("Val (built 2026-09-20 pre-render-fix).app"),
        bundle("Val (built 2026-09-20 pre-form-rule).app"),
    ]
    problems = problems_with(installed)
    assert len(problems) == 1 and "5 application bundles" in problems[0]


def test_a_preserved_build_under_another_identifier_is_not_a_duplicate() -> None:
    # Only bundles that the system could launch *as Val* count.
    kept = [bundle("Val.app"), bundle("Val (older).app", identifier=OTHER)]
    assert problems_with(kept) == []


def test_an_install_that_did_not_take_is_caught() -> None:
    problems = problems_with([bundle("Val.app", digest="a" * 64)], built_sha256="b" * 64)
    assert len(problems) == 1
    assert "the install did not take" in problems[0]
    assert "aaaaaaaaaaaaaaaa" in problems[0] and "bbbbbbbbbbbbbbbb" in problems[0]


def test_a_matching_install_passes() -> None:
    assert problems_with([bundle("Val.app", digest="c" * 64)], built_sha256="c" * 64) == []


def test_an_unreadable_executable_is_reported_rather_than_assumed_good() -> None:
    problems = problems_with([bundle("Val.app", digest=None)], built_sha256="c" * 64)
    assert len(problems) == 1 and "no readable executable" in problems[0]


def test_the_hash_comparison_waits_until_the_duplicates_are_resolved() -> None:
    # With several claiming the identifier there is no "the installed bundle" to
    # compare, and saying which one is wrong would be a guess.
    problems = problems_with([bundle("Val.app"), bundle("Val (old).app")], built_sha256="b" * 64)
    assert len(problems) == 1 and "application bundles" in problems[0]


# --- reading real directories ---------------------------------------------------------


def make_bundle(root: Path, name: str, identifier: str, body: bytes = b"binary") -> Path:
    app = root / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "val_desktop").write_bytes(body)
    (app / "Contents" / "Info.plist").write_bytes(
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<!DOCTYPE plist PUBLIC '-//Apple//DTD PLIST 1.0//EN' "
        b"'http://www.apple.com/DTDs/PropertyList-1.0.dtd'>"
        b"<plist version='1.0'><dict>"
        b"<key>CFBundleIdentifier</key><string>" + identifier.encode() + b"</string>"
        b"<key>CFBundleExecutable</key><string>val_desktop</string>"
        b"</dict></plist>"
    )
    return app


def test_it_reads_identifiers_and_binaries_out_of_a_real_directory(tmp_path: Path) -> None:
    make_bundle(tmp_path, "Val.app", IDENTIFIER, b"new")
    make_bundle(tmp_path, "Val (built 2026-09-13).app", IDENTIFIER, b"old")
    make_bundle(tmp_path, "Unrelated.app", OTHER)
    found = bundles_in(tmp_path)
    assert len(found) == 3
    ours = [b for b in found if b.identifier == IDENTIFIER]
    assert len(ours) == 2
    assert len({b.binary_sha256 for b in ours}) == 2, "two different builds, two digests"
    assert problems_with(found) != []


def test_a_bundle_without_a_readable_plist_is_skipped_not_guessed(tmp_path: Path) -> None:
    broken = tmp_path / "Broken.app"
    (broken / "Contents").mkdir(parents=True)
    (broken / "Contents" / "Info.plist").write_bytes(b"not a plist")
    make_bundle(tmp_path, "Val.app", IDENTIFIER)
    found = bundles_in(tmp_path)
    assert [b.path.name for b in found] == ["Val.app"]


def test_a_missing_directory_is_simply_empty(tmp_path: Path) -> None:
    assert bundles_in(tmp_path / "nothing-here") == []
