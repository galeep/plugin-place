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


def survey(config):
    """[(upstream_name, recorded, actual, [doc names]), ...] in plugins.yaml order."""
    rows = []
    for name, up in config["upstreams"].items():
        root = REPO_ROOT / up["submodule"]
        rows.append(
            (
                name,
                up.get(KEY),
                licenses.fingerprint_docs(root),
                [p.name for p in licenses.license_docs(root)],
            )
        )
    return rows


def drifted(rows):
    """Rows whose recorded fingerprint is absent or stale.

    A missing fingerprint counts as drift: an upstream added without one has
    never been reviewed, and treating "unset" as "fine" would let a new
    upstream opt out of the tripwire by omission.
    """
    return [r for r in rows if r[1] != r[2]]


def report(rows) -> str:
    """Markdown drift report, suitable for a PR body or a job summary."""
    bad = drifted(rows)
    if not bad:
        return "License documents unchanged at every pinned upstream."
    lines = [
        "**Licensing documents changed upstream.** Review the terms before merging "
        "— this is a notification, not a compliance verdict.",
        "",
    ]
    for name, recorded, actual, docs in bad:
        what = "no fingerprint recorded yet" if recorded is None else f"was `{recorded[:12]}`"
        lines.append(f"- `{name}`: {what}, now `{actual[:12]}` — documents: {', '.join(docs) or 'none'}")
    return "\n".join(lines)


def write_fingerprints(rows) -> int:
    """Record current fingerprints in plugins.yaml, preserving formatting.

    Line-walking rather than a YAML round-trip: dumping the parsed document
    would strip the comments that carry this file's rationale. Tracks the
    current upstream by indentation so the four identical `license: MIT` lines
    cannot be confused for one another.
    """
    src = PLUGINS_YAML.read_text()
    lines = src.splitlines(keepends=True)
    want = {name: actual for name, _, actual, _ in rows}

    out = []
    current = None
    in_upstreams = False
    pending = dict(want)
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("upstreams:"):
            in_upstreams = True
            out.append(line)
            continue
        # Any other column-0 key ends the upstreams block.
        if in_upstreams and stripped and not stripped[0].isspace():
            in_upstreams = False
            current = None
        if in_upstreams:
            # Two-space indent = an upstream key ("  caveman:").
            if stripped.startswith("  ") and not stripped.startswith("    ") and stripped.endswith(":"):
                current = stripped.strip().rstrip(":")
            elif current and stripped.strip().startswith(f"{KEY}:"):
                # Replace an existing value, keeping the original indentation.
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{KEY}: {want[current]}\n")
                pending.pop(current, None)
                continue
            elif current and stripped.strip().startswith("license:") and current in pending:
                # Insert immediately after `license:` so the two sit together.
                out.append(line)
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{KEY}: {pending.pop(current)}\n")
                continue
        out.append(line)

    if pending:
        raise SystemExit(
            f"license-fingerprint: could not place fingerprints for {sorted(pending)} "
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
    args = ap.parse_args()
    if not (args.check or args.write):
        ap.error("pass --check or --write")

    config = yaml.safe_load(PLUGINS_YAML.read_text())
    rows = survey(config)

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
