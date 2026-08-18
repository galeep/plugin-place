#!/usr/bin/env python3
"""license-fingerprint.py — report and record upstream licensing-document drift.

WHY THIS EXISTS
    The `license:` value in plugins.yaml is a static human declaration. Nothing
    in the build ever compared it against what the upstream actually ships, so
    an upstream relicense moved through silently. caveman v2.1.0 did exactly
    that (MIT -> split MIT + BSL-1.1): it edited LICENSE and added LICENSE.BSL
    and LICENSING.md, and the nightly sync workflow's review summary counts
    `plugins/<name>/LICENSE` as one anonymous increment to its "asset/other"
    file tally. A relicense was indistinguishable from a README typo fix.

FAIL DIRECTION — deliberately NOT the patch-anchor idiom
    A drifted patch anchor aborts the build, because the build OUTPUT would be
    wrong (an unpatched plugin would publish). A changed license does not make
    the output wrong; it makes a DECLARATION possibly stale. Those differ, and
    the remedy differs too.

    So this never aborts. Hard-failing would mean any upstream touching a
    copyright year turns the nightly red and suppresses that day's sync PR
    entirely — trading a silent relicense for a silent sync outage, which is
    the worse failure for a workflow whose whole job is telling a human that
    third-party code moved.

    Instead the signal is routed to where a human already looks: the sync PR
    body. A warning that only ever lands in a green cron's log is unobservable,
    which is the same trap sync-upstream.yml documents for its dedupe gate.

MODES
    --check   Print a drift report. Exit 0 always (advisory), unless --strict.
    --strict  With --check, exit 1 on drift. For an explicit gate; nothing in
              the nightly path uses it.
    --write   Recompute every fingerprint and record it in plugins.yaml,
              inserting the key when absent. The sync workflow runs this after
              bumping pins, so the PR carries the new fingerprint and the
              plugins.yaml diff shows the change alongside the report.

SCOPE, stated plainly
    Detects changes to licensing DOCUMENTS at an upstream's root. It does not
    parse per-directory license tables and cannot see a new subdirectory that
    inherits a restrictive default without any document changing. It catches
    the case that actually occurred and turns it from silent into loud. It is
    not a compliance audit.
"""
import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from scripts.lib import licenses  # noqa: E402

PLUGINS_YAML = REPO_ROOT / "plugins.yaml"
KEY = "license_fingerprint"


def survey(config, only=None):
    """[(upstream_name, recorded, actual, docs), ...] in plugins.yaml order.

    `actual` is None and `docs` is None when the submodule is not checked out.
    `only` restricts to named upstreams (see --upstream).
    """
    rows = []
    for name, up in config["upstreams"].items():
        if only and name not in only:
            continue
        root = REPO_ROOT / up["submodule"]
        docs = licenses.license_docs(root)
        rows.append(
            (
                name,
                up.get(KEY),
                licenses.fingerprint_docs(root),
                None if docs is None else [p.name for p in docs],
            )
        )
    return rows


def unreadable(rows):
    """Rows whose submodule is not checked out, so nothing can be verified."""
    return [r for r in rows if r[2] is None]


def drifted(rows):
    """Rows whose recorded fingerprint is absent or stale.

    A missing fingerprint counts as drift: an upstream added without one has
    never been reviewed, and treating "unset" as "fine" would let a new
    upstream opt out of the tripwire by omission.

    Unreadable rows are NOT drift — they are unverifiable, reported separately.
    Calling them drift would invite a `--write` that records the empty-tree hash
    and disarms the tripwire for good.
    """
    return [r for r in rows if r[2] is not None and r[1] != r[2]]


def report(rows) -> str:
    """Markdown drift report, suitable for a PR body or a job summary."""
    bad = drifted(rows)
    blind = unreadable(rows)
    if not bad and not blind:
        return "License documents unchanged at every pinned upstream."

    lines = []
    if bad:
        lines += [
            "**Licensing documents changed upstream.** Review the terms before merging "
            "— this is a notification, not a compliance verdict.",
            "",
        ]
        for name, recorded, actual, docs in bad:
            was = (
                "no fingerprint recorded yet"
                if recorded is None
                else f"was `{str(recorded)[:12]}`"
            )
            lines.append(
                f"- `{name}`: {was}, now `{actual[:12]}` — documents: "
                f"{', '.join(docs) or 'none'}"
            )
    if blind:
        if lines:
            lines.append("")
        lines.append(
            "**Not verified** (submodule not checked out — run "
            "`git submodule update --init`): "
            + ", ".join(f"`{r[0]}`" for r in blind)
        )
    return "\n".join(lines)


def _upstream_at(line):
    """The upstream key a line declares ("  caveman:" -> "caveman"), else None.

    Exactly two spaces of indent: deeper lines are that upstream's fields.
    """
    stripped = line.rstrip("\n")
    if (
        stripped.startswith("  ")
        and not stripped.startswith("   ")
        and stripped.rstrip().endswith(":")
    ):
        return stripped.strip().rstrip(":")
    return None


def _scan_blocks(lines):
    """{upstream: has_fingerprint_key} for the upstreams block.

    A SEPARATE PASS is the whole point. One pass cannot work: `license:` sits
    ABOVE `license_fingerprint:` in every entry, so when the writer reaches
    `license:` it does not yet know whether a fingerprint line follows. The
    original version guessed "no" and inserted, then hit the existing line lower
    down and rewrote that too — turning one key into two on EVERY run
    (4 lines -> 8 -> 12 -> 16, unbounded). yaml.safe_load accepts duplicate keys
    silently with last-wins, so nothing downstream complained, and the sync
    workflow runs --write nightly: the first nightly after merge would have
    corrupted plugins.yaml.
    """
    seen = {}
    current = None
    in_upstreams = False
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("upstreams:"):
            in_upstreams = True
            continue
        if in_upstreams and stripped and not stripped[0].isspace():
            break  # a new column-0 key ends the upstreams block
        if not in_upstreams:
            continue
        key = _upstream_at(line)
        if key is not None:
            current = key
            seen.setdefault(current, False)
        elif current and stripped.strip().startswith(f"{KEY}:"):
            seen[current] = True
    return seen


def write_fingerprints(rows) -> int:
    """Record current fingerprints in plugins.yaml, preserving formatting.

    Line-walking rather than a YAML round-trip: dumping the parsed document
    would strip the comments that carry this file's rationale.

    Refuses to record anything while any surveyed submodule is not checked out.
    Recording the empty-tree hash there would read as "verified clean" on every
    later check — see licenses.license_docs for why that is the failure that
    matters.
    """
    blind = unreadable(rows)
    if blind:
        raise SystemExit(
            "license-fingerprint: refusing to record fingerprints while "
            + ", ".join(r[0] for r in blind)
            + " is not checked out — the recorded value would be the hash of an "
            "empty tree, which reads as 'verified clean' forever after. "
            "Run: git submodule update --init"
        )

    src = PLUGINS_YAML.read_text()
    lines = src.splitlines(keepends=True)
    blocks = _scan_blocks(lines)
    want = {name: actual for name, _, actual, _ in rows}

    missing = [n for n in want if n not in blocks]
    if missing:
        raise SystemExit(
            f"license-fingerprint: no upstreams entry found for {sorted(missing)} "
            f"in plugins.yaml"
        )

    out = []
    current = None
    in_upstreams = False
    placed = set()
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("upstreams:"):
            in_upstreams = True
            out.append(line)
            continue
        if in_upstreams and stripped and not stripped[0].isspace():
            in_upstreams = False
            current = None
        if in_upstreams:
            key = _upstream_at(line)
            if key is not None:
                current = key
            elif current in want and stripped.strip().startswith(f"{KEY}:"):
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{KEY}: {want[current]}\n")
                placed.add(current)
                continue
            elif (
                current in want
                and not blocks[current]
                and stripped.strip().startswith("license:")
            ):
                # Insert ONLY where the scan proved no key exists further down.
                out.append(line)
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{KEY}: {want[current]}\n")
                placed.add(current)
                continue
        out.append(line)

    unplaced = sorted(set(want) - placed)
    if unplaced:
        raise SystemExit(
            f"license-fingerprint: could not place fingerprints for {unplaced} "
            f"— no `license:` line found under those upstreams in plugins.yaml"
        )

    new = "".join(out)
    if new == src:
        return 0
    PLUGINS_YAML.write_text(new)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="print a drift report")
    ap.add_argument("--strict", action="store_true", help="with --check, exit 1 on drift")
    ap.add_argument("--write", action="store_true", help="record current fingerprints")
    ap.add_argument(
        "--upstream",
        action="append",
        metavar="NAME",
        help="limit to this upstream (repeatable). Without it --write records ALL "
        "four at once, so someone who reviewed only caveman's terms would silently "
        "bless unread drift in the other three.",
    )
    args = ap.parse_args()
    if not (args.check or args.write):
        ap.error("pass --check or --write")

    config = yaml.safe_load(PLUGINS_YAML.read_text())
    known = set(config["upstreams"])
    if args.upstream:
        unknown = sorted(set(args.upstream) - known)
        if unknown:
            ap.error(f"unknown upstream(s): {unknown}; known: {sorted(known)}")
    rows = survey(config, only=set(args.upstream) if args.upstream else None)

    if args.check:
        print(report(rows))
        if args.strict and drifted(rows):
            return 1
    if args.write:
        changed = write_fingerprints(rows)
        print(
            "license-fingerprint: plugins.yaml updated"
            if changed
            else "license-fingerprint: already current"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
