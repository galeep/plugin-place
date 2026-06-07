"""Load assignment tables and enforce the coverage gate.

The gate is the guarantee that no upstream item is ever silently dropped:
every present item must be assigned to a real plugin, and the table must not
carry stale entries for items that left upstream.
"""
import yaml


def load_table(path):
    """Load a `<slug>: <plugin>` YAML mapping; empty/missing file -> {}."""
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        return {}
    return data or {}


def members_for(table, plugin_name):
    """Sorted slugs assigned to `plugin_name`."""
    return sorted(s for s, p in table.items() if p == plugin_name)


def coverage_gate(present_items, table, valid_plugins, kind):
    """Abort (SystemExit) with every problem listed if the table does not exactly
    and validly cover `present_items`.

    present_items: set of slugs found in the submodule.
    table:        dict slug -> plugin (or 'UNASSIGNED').
    valid_plugins: set of plugin names declared in plugins.yaml.
    kind:         'skill' | 'agent', for messages.
    """
    errors = []
    for item in sorted(present_items):
        if item not in table:
            errors.append(f"{kind} {item!r}: not in assignment table")
        elif not table[item] or table[item] == "UNASSIGNED":
            errors.append(f"{kind} {item!r}: UNASSIGNED")
        elif table[item] not in valid_plugins:
            errors.append(
                f"{kind} {item!r}: plugin {table[item]!r} not declared in plugins.yaml"
            )
    for item in sorted(table):
        if item not in present_items:
            errors.append(f"{kind} {item!r}: in table but not in submodule (stale)")
    if errors:
        raise SystemExit("coverage gate FAILED:\n  " + "\n  ".join(errors))
