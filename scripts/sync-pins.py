#!/usr/bin/env python3
"""Print a canonical, comparable pin map from a plugins.yaml.

Used by the sync workflow's dedupe gate to decide whether an open sync PR
already proposes the same upstream bump.

DESIGN RATIONALE: compares PINS, not whole trees. A tree comparison is
base-dependent — any unrelated commit landing on main changes the regenerated
tree, so the gate stops matching and duplicates resume. It would only hold
while main is frozen, which is exactly when nobody needs it. The pin set is
what the proposal actually *is*, and it is invariant under base drift.

Reads a path argument, or stdin when passed '-'. Emits one "<key>=<tag>" line
per upstream, sorted by key so output is order-stable across runs.

Exits nonzero on any parse failure rather than printing an empty map, so the
caller can distinguish "this file pins nothing" from "I could not read this
file". Those must not collapse: the second silently defeats the gate.
"""
import sys

import yaml

UNPINNED = "-"  # sentinel: upstream carries neither pinned_tag nor pinned_sha


def pin_map(stream):
    data = yaml.safe_load(stream)
    upstreams = (data or {}).get("upstreams")
    if not isinstance(upstreams, dict) or not upstreams:
        raise ValueError("no non-empty 'upstreams' block")
    lines = []
    for key in sorted(upstreams):
        cfg = upstreams[key] or {}
        if not isinstance(cfg, dict):
            raise ValueError(f"upstream {key!r} is not a mapping")
        tag = cfg.get("pinned_tag")
        sha = cfg.get("pinned_sha")
        # Emit whichever pin the upstream actually uses. Both kinds must appear
        # as their real value: collapsing SHA-pinned upstreams to a single
        # sentinel would make two DIFFERENT sha pins compare equal, and the
        # dedupe gate would then suppress a proposal that genuinely differs.
        # The cron only advances tag-pinned upstreams, but sha pins move by hand
        # and a hand-bumped sha can ride along in a sync PR.
        # Prefixed so a tag and a sha can never collide in the same namespace.
        if tag:
            value = f"tag:{tag}"
        elif sha:
            value = f"sha:{sha}"
        else:
            value = UNPINNED
        lines.append(f"{key}={value}")
    return lines


def main(argv):
    if len(argv) != 2:
        sys.exit(f"usage: {argv[0]} <plugins.yaml|->")
    try:
        if argv[1] == "-":
            lines = pin_map(sys.stdin)
        else:
            with open(argv[1], encoding="utf-8") as fh:
                lines = pin_map(fh)
    except Exception as exc:  # noqa: BLE001 — any failure must be loud, not empty
        sys.exit(f"sync-pins: {argv[1]}: {exc}")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv)
