"""CLAUDE.md's "Current work" restates the newest scope ruling, or CI is red.

Approved by Lord Armand, 1 September 2026, after an external reviewer found
`CLAUDE.md` still saying "Layer 0 only" while the 31 August ruling in the
baselines permitted Layer 1 presence in parallel — two governing documents in
contradiction, found the most expensive way anything is found. A convention
("update both in the same commit") is not a control; this is the control.

## The marker convention

Every scope-affecting ruling recorded in `docs/baselines/` carries a
machine-readable marker line, invisible in rendered Markdown:

    <!-- scope-ruling: 2026-08-31 -->

`CLAUDE.md` carries the marker of the ruling its "Current work" section
restates. This check fails when the newest marker anywhere in the baselines is
newer than the one `CLAUDE.md` carries — the exact moment a recorded ruling
has not been brought into step — and when either side carries no marker at
all, so the mechanism cannot be silently retired by deleting its inputs.

The comparison is exact dates, no prose parsing: a ruling is in step or it is
not, and the failure message says which document moved.

## The controlled set is narrow, deliberately

Ruled 1 September 2026: tripwire **temporary rulings and duplicated
scope/status facts that must move together**; test behavioral invariants;
minimize semantic duplication everywhere else. Matching markers prove
synchronization of markers, not of meaning — two documents can carry the same
date and contradict each other — so this file does not grow a marker for
every cross-document restatement.

Second controlled item, same date: **the strip-routing deviation.**
`02-partner-systems.md` §4.1 routes the strip step locally; `04-layer-0.md`
§4 sends it to the cheapest Protected-eligible cloud route until local
inference exists. The deviation carries its own expiry, and temporary
deviations with built-in invalidation conditions are exactly the rules that
become permanent by accident. The pairing enforced: the deviation marker in
`04-layer-0.md` must be present while the Model Configuration Registry holds
no local route, and must be gone (the section moved) once it holds one — a
provider outside the known cloud set is the machine-detectable form of "local
inference exists."
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The marker every scope-affecting ruling carries. ISO dates compare
#: correctly as strings, which is the whole trick.
MARKER = re.compile(r"<!--\s*scope-ruling:\s*(\d{4}-\d{2}-\d{2})\s*-->")

#: The strip-routing deviation's marker (04-layer-0.md §4).
DEVIATION_MARKER = "<!-- deviation: strip-routing-cloud-until-local -->"

#: Providers with cloud adapters today. A registry provider outside this set
#: is a local (or at least non-cloud) route, which is the deviation's
#: built-in invalidation condition made machine-detectable.
#:
#: **Maintenance is bound to provider admission** (ruled 1 September 2026,
#: after registry inspection found no authoritative execution-locality field —
#: and `RULED_PROVIDERS` cannot serve, because a local route will also need a
#: ruling and would join it). Admitting a new CLOUD provider updates this
#: roster in the same commit as its eligibility ruling; the reminder sits on
#: `RULED_PROVIDERS` in `val_policy/eligibility.py`, the line that commit must
#: touch anyway. Failure to update is a false RED, not a false green: the
#: check misreads the new cloud provider as local and demands the strip
#: deviation move, with the fix named in the message.
CLOUD_PROVIDERS = frozenset({"anthropic", "openai", "google"})

_PROVIDER = re.compile(r'provider="([a-z0-9_-]+)"')


def markers_in(text: str) -> list[str]:
    """Every scope-ruling date in one document, as written."""
    return MARKER.findall(text)


def check_strip_deviation(layer0_md: Path, registry_py: Path) -> list[str]:
    """The strip-routing deviation expires when a local route exists — enforced.

    Marker present + no local route: the deviation stands, correctly.
    Marker present + a local route: **the deviation has expired** and
    `04-layer-0.md` §4 has not moved — the failure this exists to catch.
    Marker absent + no local route: the deviation text was removed while its
    condition still holds — the record no longer states the routing that is
    actually happening.
    """
    problems: list[str] = []
    deviation_stands = DEVIATION_MARKER in layer0_md.read_text(encoding="utf-8")
    non_cloud = sorted(
        provider
        for provider in set(_PROVIDER.findall(registry_py.read_text(encoding="utf-8")))
        if provider not in CLOUD_PROVIDERS
    )

    if deviation_stands and non_cloud:
        problems.append(
            f"the strip-routing deviation (04-layer-0.md §4) has expired: the Model "
            f"Configuration Registry now holds non-cloud provider(s) {non_cloud}, so "
            "local inference exists and the strip step must move to it "
            "(02-partner-systems.md §4.1). Amend §4 and remove its deviation marker "
            "— a temporary deviation does not get to become permanent by accident. "
            "(If this provider is actually a NEW CLOUD provider, this is the bound "
            "maintenance firing: add it to CLOUD_PROVIDERS in "
            "infrastructure/ci/check_scope_ruling.py in the same commit as its "
            "eligibility ruling.)"
        )
    if not deviation_stands and not non_cloud:
        problems.append(
            "04-layer-0.md no longer carries the strip-routing deviation marker, but "
            "the registry still holds only cloud providers — the strip step is still "
            "routed to the cloud, and the record must say so. Restore the deviation "
            "(and its marker), or stand up the local route it defers to."
        )
    return problems


def check(baselines_dir: Path, claude_md: Path) -> list[str]:
    """Everything out of step, as printable problems. Empty means in step."""
    problems: list[str] = []

    newest_date = ""
    newest_where = ""
    for path in sorted(baselines_dir.glob("*.md")):
        for date in markers_in(path.read_text(encoding="utf-8")):
            if date > newest_date:
                newest_date, newest_where = date, path.name
    if not newest_date:
        problems.append(
            f"no scope-ruling marker found anywhere in {baselines_dir}: the "
            "tripwire has no baseline input. Every scope-affecting ruling "
            "carries `<!-- scope-ruling: YYYY-MM-DD -->` (ruling, 1 September 2026)."
        )

    stated = markers_in(claude_md.read_text(encoding="utf-8"))
    if not stated:
        problems.append(
            f"{claude_md.name} carries no scope-ruling marker: its Current work "
            "section must name the ruling it restates."
        )

    if problems:
        return problems

    newest_stated = max(stated)
    if newest_stated < newest_date:
        problems.append(
            f"{claude_md.name} restates the scope ruling of {newest_stated}, but "
            f"{newest_where} records a newer one dated {newest_date}. Bring "
            "CLAUDE.md's Current work section into step with the ruling — the "
            "baselines govern, and a stale restatement is a governing document "
            "contradicting another."
        )
    elif newest_stated > newest_date:
        problems.append(
            f"{claude_md.name} claims a scope ruling dated {newest_stated} that no "
            "baseline records (newest recorded: "
            f"{newest_date} in {newest_where}). The restatement cannot be "
            "ahead of the record."
        )
    return problems


def main() -> int:
    problems = check(REPO_ROOT / "docs" / "baselines", REPO_ROOT / "CLAUDE.md")
    problems.extend(
        check_strip_deviation(
            REPO_ROOT / "docs" / "baselines" / "04-layer-0.md",
            REPO_ROOT / "packages" / "domain" / "src" / "val_domain" / "registry.py",
        )
    )
    if problems:
        print("CLAUDE.md is out of step with the recorded scope ruling:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(
        "CLAUDE.md restates the newest recorded scope ruling, and the controlled "
        "deviation stands consistently with the registry."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
