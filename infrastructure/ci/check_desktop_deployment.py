"""One machine, one Val: the installed desktop must be unambiguous.

Owner acceptance failure, 21 September 2026. Lord Armand quit the desktop,
reopened it, opened the conversation holding the persisted image, and the image
did not appear — after a build that demonstrably renders it.

The cause was not the renderer, the policy, the byte route or the substrate. It
was **deployment**. Four earlier builds had been kept beside the current one in
`/Applications`, every one of them carrying the same `CFBundleIdentifier`. macOS
resolves an application by identifier, not by name, so `open -b house.armand.val`
— which is what the Dock, Spotlight and a relaunch all ultimately do — started
whichever copy LaunchServices happened to prefer. It preferred the build of 13
September, whose content security policy predates the image work and refuses the
governed byte origin outright. The request was therefore never made, which is
exactly what the service log showed.

Preserving a previous build is right. Leaving it somewhere the system may launch
it instead is the defect: it makes "the installed build" a thing nobody can point
at, and it makes every acceptance result unattributable. A preserved build lives
outside the launchable locations.

**What this check cannot do.** It runs on the machine that has the desktop
installed, so CI on Linux skips it. The engine-level question — whether the
packaged WebView actually loads the image under the shipped policy — is a
macOS-only manual check; `infrastructure/desktop/packaged_render_check.swift`
performs it, and the final word remains Lord Armand's own acceptance.
"""

from __future__ import annotations

import hashlib
import plistlib
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The desktop's identifier, as the shipped Tauri configuration declares it.
IDENTIFIER = "house.armand.val"

#: Where macOS looks for applications to launch. A bundle anywhere here is a
#: bundle the system may choose; a bundle anywhere else is an archive.
LAUNCHABLE = (Path("/Applications"), Path.home() / "Applications")

#: The bundle a fresh `tauri build` produces.
BUILT = REPO_ROOT / "apps/desktop/src-tauri/target/release/bundle/macos/Val.app"


@dataclass(frozen=True)
class Bundle:
    """One application bundle found in a launchable location."""

    path: Path
    identifier: str
    binary_sha256: str | None


def digest_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def bundles_in(directory: Path) -> list[Bundle]:
    """Every `.app` directly inside one launchable location."""
    found: list[Bundle] = []
    if not directory.is_dir():
        return found
    for entry in sorted(directory.glob("*.app")):
        info = entry / "Contents" / "Info.plist"
        try:
            with info.open("rb") as handle:
                plist = plistlib.load(handle)
        except OSError, plistlib.InvalidFileException:
            continue
        identifier = str(plist.get("CFBundleIdentifier", ""))
        executable = plist.get("CFBundleExecutable")
        binary = entry / "Contents" / "MacOS" / str(executable) if executable else None
        found.append(
            Bundle(
                path=entry,
                identifier=identifier,
                binary_sha256=digest_of(binary) if binary else None,
            )
        )
    return found


def problems_with(bundles: list[Bundle], built_sha256: str | None = None) -> list[str]:
    """Everything wrong with what is launchable, said plainly.

    Pure, so the rule can be tested without an installed application and without
    a Mac — which is the point, since the failure it encodes was found on one
    machine and must not depend on that machine to stay found.
    """
    problems: list[str] = []
    ours = [bundle for bundle in bundles if bundle.identifier == IDENTIFIER]

    if len(ours) > 1:
        listed = ", ".join(sorted(str(bundle.path) for bundle in ours))
        problems.append(
            f"{len(ours)} application bundles in launchable locations carry the identifier "
            f"{IDENTIFIER}: {listed}. macOS resolves an application by identifier, so which "
            "one opens is not decided by its name and not decided by you — a relaunch may "
            "start any of them, and an acceptance result then belongs to no known build. "
            "Keep exactly one installed and move every preserved build outside "
            "/Applications and ~/Applications."
        )

    if built_sha256 is not None and len(ours) == 1:
        installed = ours[0].binary_sha256
        if installed is None:
            problems.append(f"{ours[0].path} has no readable executable to compare.")
        elif installed != built_sha256:
            problems.append(
                f"the installed bundle {ours[0].path} carries binary {installed[:16]} but the "
                f"last build produced {built_sha256[:16]}. The build succeeded and the install "
                "did not take, so what is running is not what was just proven."
            )
    return problems


def main() -> int:
    if sys.platform != "darwin":
        print("desktop deployment: skipped, this check runs on the machine that installs it")
        return 0

    bundles: list[Bundle] = []
    for directory in LAUNCHABLE:
        bundles.extend(bundles_in(directory))

    built = BUILT / "Contents" / "MacOS" / "val_desktop"
    problems = problems_with(bundles, digest_of(built) if built.exists() else None)

    if problems:
        print("the installed desktop is ambiguous:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    ours = [bundle for bundle in bundles if bundle.identifier == IDENTIFIER]
    if not ours:
        print(f"desktop deployment: no bundle with {IDENTIFIER} is installed")
        return 0
    print(f"desktop deployment: one installed bundle, {ours[0].path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
