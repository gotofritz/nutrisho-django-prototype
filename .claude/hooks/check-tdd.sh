#!/usr/bin/env bash
# Block writing a TypeScript/Svelte source module when no matching test exists.
#
# Copied from anklipper (#162) and scoped to extension/: nothing else in this
# repository is gated, and only a test under extension/ counts.
#
# A module `foo.ts` / `Foo.svelte` is satisfied by a test whose stem matches —
# `foo.test.ts`, `foo.spec.ts`, `Foo.svelte.test.ts` — found as a sibling, in a
# sibling `__tests__/`, or anywhere in extension/ (mirrored `tests/` trees count).
#
# Escape hatch: SKIP_TDD_HOOK=1. AGENTS.md allows skipping TDD only for
# throwaway prototypes, generated code, and config — ask first.
set -uo pipefail

[[ "${SKIP_TDD_HOOK:-}" == "1" ]] && exit 0

FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[[ -n "$FILE" ]] || exit 0

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
REL="${FILE#"$ROOT"/}"

# --- only the extension is gated --------------------------------------------
case "$REL" in
  extension/*) ;;
  *) exit 0 ;;
esac
EXT="$ROOT/extension"

BASE=$(basename "$REL")
DIR=$(dirname "$REL")

# --- only TypeScript and Svelte source is gated -----------------------------
case "$BASE" in
  *.ts | *.tsx | *.svelte) ;;
  *) exit 0 ;;
esac

# --- test files, mocks, and fixtures are never gated ------------------------
case "$BASE" in
  *.test.* | *.spec.* | *.d.ts) exit 0 ;;
esac
case "/$REL/" in
  */__tests__/* | */__mocks__/* | */fixtures/* | */tests/* | */test/* | */e2e/*)
    exit 0 ;;
esac

# --- config, ambient types, barrels, and thin entrypoints -------------------
# `preview/` is an entrypoint by another name: it mounts a component against
# the port fakes so the skin can be looked at. Same rule applies — keep
# behaviour out of it, or it belongs in `src/` with a test.
case "$BASE" in
  *.config.ts | *.config.js | *.setup.ts | *.types.ts | types.ts | index.ts)
    exit 0 ;;
esac
case "/$REL/" in
  */entrypoints/* | */preview/*) exit 0 ;;
esac

# --- generated, vendored, and tooling trees ---------------------------------
case "/$REL/" in
  */node_modules/* | */dist/* | */build/* | */coverage/* | */.output/* | */.wxt/* | */.svelte-kit/* | */.git/* | */.claude/* | */docs/*)
    exit 0 ;;
esac

# --- does a matching test exist? --------------------------------------------
# `draft.ts` -> draft ; `CardEditor.svelte` -> CardEditor (also CardEditor.svelte)
STEM="${BASE%.*}"

has_test() {
  local stem="$1" dir
  for dir in "$ROOT/$DIR" "$ROOT/$DIR/__tests__"; do
    compgen -G "$dir/$stem.test.*" >/dev/null && return 0
    compgen -G "$dir/$stem.spec.*" >/dev/null && return 0
  done
  # anywhere else in the extension — mirrored tests/ trees, colocated suites
  local hit
  hit=$(find "$EXT" \
    -type d \( -name node_modules -o -name .git -o -name dist -o -name build \
               -o -name coverage -o -name .output -o -name .wxt -o -name .svelte-kit \) -prune -o \
    -type f \( -name "$stem.test.*" -o -name "$stem.spec.*" \) -print -quit 2>/dev/null)
  [[ -n "$hit" ]]
}

if has_test "$STEM"; then exit 0; fi
# Foo.svelte may be covered by Foo.svelte.test.ts
[[ "$BASE" == *.svelte ]] && has_test "$BASE" && exit 0

# --- block ------------------------------------------------------------------
jq -nc --arg stem "$STEM" --arg rel "$REL" \
  '{continue:false,
    stopReason:("TDD violation: no test covers \($rel). Write \($stem).test.ts FIRST (sibling, __tests__/, or tests/), watch it fail, then implement.")}'
exit 0
