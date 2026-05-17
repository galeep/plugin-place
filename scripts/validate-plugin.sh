#!/bin/bash
# Plugin Structure Validator
# Validates overall plugin structure, manifest, and cross-references
#
# Usage: validate-plugin.sh <plugin-directory>
# Source: cc-plugin-dev skill (galeep's local copy)

set -uo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: $0 <plugin-directory>"
  exit 1
fi

PLUGIN_DIR="$1"

if [ ! -d "$PLUGIN_DIR" ]; then
  echo "❌ Error: Not a directory: $PLUGIN_DIR"
  exit 1
fi

echo "🔍 Validating plugin: $PLUGIN_DIR"
echo ""

error_count=0
warning_count=0

# --- Manifest ---
echo "Checking manifest..."

MANIFEST="$PLUGIN_DIR/.claude-plugin/plugin.json"

if [ ! -f "$MANIFEST" ]; then
  echo "❌ Missing .claude-plugin/plugin.json"
  error_count=$((error_count + 1))
else
  if ! jq empty "$MANIFEST" 2>/dev/null; then
    echo "❌ plugin.json is not valid JSON"
    error_count=$((error_count + 1))
  else
    echo "✅ Valid JSON"

    NAME=$(jq -r '.name // empty' "$MANIFEST")
    if [ -z "$NAME" ]; then
      echo "❌ Missing required field: name"
      error_count=$((error_count + 1))
    else
      echo "✅ name: $NAME"
      if ! [[ "$NAME" =~ ^[a-z][a-z0-9-]*[a-z0-9]$ ]] && ! [[ "$NAME" =~ ^[a-z][a-z0-9]*$ ]]; then
        echo "❌ name must be kebab-case"
        error_count=$((error_count + 1))
      fi
    fi

    VERSION=$(jq -r '.version // empty' "$MANIFEST")
    if [ -z "$VERSION" ]; then
      echo "⚠️  Missing recommended field: version"
      warning_count=$((warning_count + 1))
    elif ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "⚠️  version '$VERSION' does not follow semver"
      warning_count=$((warning_count + 1))
    else
      echo "✅ version: $VERSION"
    fi

    DESC=$(jq -r '.description // empty' "$MANIFEST")
    if [ -z "$DESC" ]; then
      echo "⚠️  Missing recommended field: description"
      warning_count=$((warning_count + 1))
    else
      echo "✅ description present"
    fi
  fi
fi

# --- Directory structure ---
echo ""
echo "Checking directory structure..."

if [ -d "$PLUGIN_DIR/.claude-plugin/commands" ]; then
  echo "❌ commands/ is inside .claude-plugin/ — must be at plugin root"
  error_count=$((error_count + 1))
fi
if [ -d "$PLUGIN_DIR/.claude-plugin/agents" ]; then
  echo "❌ agents/ is inside .claude-plugin/ — must be at plugin root"
  error_count=$((error_count + 1))
fi
if [ -d "$PLUGIN_DIR/.claude-plugin/skills" ]; then
  echo "❌ skills/ is inside .claude-plugin/ — must be at plugin root"
  error_count=$((error_count + 1))
fi

for comp_dir in commands agents skills hooks scripts; do
  if [ -d "$PLUGIN_DIR/$comp_dir" ]; then
    count=$(find "$PLUGIN_DIR/$comp_dir" -type f 2>/dev/null | wc -l | tr -d ' ')
    echo "✅ $comp_dir/ present ($count files)"
  fi
done

if [ -f "$PLUGIN_DIR/.mcp.json" ]; then
  if jq empty "$PLUGIN_DIR/.mcp.json" 2>/dev/null; then
    echo "✅ .mcp.json present and valid JSON"
  else
    echo "❌ .mcp.json is not valid JSON"
    error_count=$((error_count + 1))
  fi
fi

if [ -d "$PLUGIN_DIR/skills" ]; then
  echo ""
  echo "Checking skills..."
  missing=0
  total=0
  while IFS= read -r skill_dir; do
    total=$((total + 1))
    if [ ! -f "$skill_dir/SKILL.md" ]; then
      echo "❌ skills/$(basename "$skill_dir")/ missing SKILL.md"
      missing=$((missing + 1))
      error_count=$((error_count + 1))
    fi
  done < <(find "$PLUGIN_DIR/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
  if [ "$missing" -eq 0 ] && [ "$total" -gt 0 ]; then
    echo "✅ all $total skill dirs have SKILL.md"
  fi
fi

echo ""
if [ -f "$PLUGIN_DIR/README.md" ]; then
  echo "✅ README.md present"
else
  echo "⚠️  Missing README.md"
  warning_count=$((warning_count + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $error_count -eq 0 ] && [ $warning_count -eq 0 ]; then
  echo "✅ All checks passed!"
  exit 0
elif [ $error_count -eq 0 ]; then
  echo "⚠️  Passed with $warning_count warning(s)"
  exit 0
else
  echo "❌ Failed: $error_count error(s), $warning_count warning(s)"
  exit 1
fi
