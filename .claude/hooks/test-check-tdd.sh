#!/usr/bin/env bash
# Tests for check-tdd.sh. Run: bash .claude/hooks/test-check-tdd.sh (or make test-hooks)
#
# Copied from anklipper, with every gated path under extension/: the hook
# checks the extension's TypeScript and Svelte and nothing else (#162).
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/check-tdd.sh"
PASS=0
FAIL=0

# run <expect: allow|block> <description> <file_path> [files to pre-create...]
run() {
  local expect="$1" desc="$2" file="$3"
  shift 3

  local sandbox
  sandbox=$(mktemp -d)
  ( cd "$sandbox" && git init -q . )

  # the target file itself exists for Edit-like cases only when listed below
  for f in "$@"; do
    mkdir -p "$sandbox/$(dirname "$f")"
    : > "$sandbox/$f"
  done
  mkdir -p "$sandbox/$(dirname "$file")"

  local out actual
  out=$(cd "$sandbox" && printf '{"tool_input":{"file_path":"%s"}}' "$sandbox/$file" \
    | bash "$HOOK" 2>/dev/null)

  if [[ -z "$out" ]]; then
    actual=allow
  elif grep -q '"continue":false' <<<"$out"; then
    actual=block
  else
    actual=allow
  fi

  if [[ "$actual" == "$expect" ]]; then
    PASS=$((PASS + 1))
    printf '  ok   %s\n' "$desc"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL %s (expected %s, got %s)\n' "$desc" "$expect" "$actual"
    [[ -n "$out" ]] && printf '       output: %s\n' "$out"
  fi

  rm -rf "$sandbox"
}

echo "check-tdd.sh"

# --- gated source without a test -------------------------------------------
run block "bare .ts module with no test"          extension/src/card/draft.ts
run block "bare .svelte component with no test"   extension/src/ui/CardEditor.svelte
run block "bare .tsx module with no test"         extension/src/ui/Panel.tsx

# --- test present in an accepted location ----------------------------------
run allow "sibling .test.ts"          extension/src/card/draft.ts  extension/src/card/draft.test.ts
run allow "sibling .spec.ts"          extension/src/card/draft.ts  extension/src/card/draft.spec.ts
run allow "sibling __tests__/"        extension/src/card/draft.ts  extension/src/card/__tests__/draft.test.ts
run allow "mirrored tests/ tree"      extension/src/card/draft.ts  extension/tests/card/draft.test.ts
run allow "component test"            extension/src/ui/CardEditor.svelte  extension/src/ui/CardEditor.test.ts
run allow "component .svelte.test.ts" extension/src/ui/CardEditor.svelte  extension/src/ui/CardEditor.svelte.test.ts

# a same-stem test must not satisfy a *different* module
run block "unrelated stem does not count"  extension/src/card/draft.ts  extension/src/card/render.test.ts

# --- the test files themselves ---------------------------------------------
run allow "the .test.ts itself"     extension/src/card/draft.test.ts
run allow "the .spec.ts itself"     extension/src/card/draft.spec.ts
run allow "file under tests/"       extension/tests/integration/flow.ts
run allow "file under __tests__/"   extension/src/card/__tests__/helpers.ts
run allow "file under __mocks__/"   extension/src/card/__mocks__/anki.ts
run allow "fixture file"            extension/src/card/fixtures/page.ts

# --- exempt by kind ---------------------------------------------------------
run allow "config file"       extension/wxt.config.ts
run allow "vitest config"     extension/vitest.config.ts
run allow "setup file"        extension/vitest.setup.ts
run allow "ambient types"     extension/src/globals.d.ts
run allow "types module"      extension/src/card/types.ts
run allow "suffixed types"    extension/src/card/draft.types.ts
run allow "barrel"            extension/src/card/index.ts
run allow "WXT entrypoint"    extension/entrypoints/background.ts
run allow "nested entrypoint" extension/src/entrypoints/sidepanel/main.ts
run allow "preview harness"   extension/preview/main.ts

# --- not gated at all -------------------------------------------------------
run allow "markdown"          extension/docs/plans/00-plan.md
run allow "json"              extension/package.json
run allow "css"               extension/src/app.css
run allow "generated output"  extension/dist/chunk.ts
run allow "WXT build output"  extension/.output/firefox-mv3/chunk.ts
run allow "dependency"        extension/node_modules/pkg/index.ts
run allow "hook script"       .claude/hooks/check-tdd.sh

# --- outside extension/ -----------------------------------------------------
run allow "server code"          server/src/recipes/static/js/app.ts
run allow "a .ts at the root"    scratch.ts
run block "a test outside extension/ does not count" extension/src/card/draft.ts  server/tests/draft.test.ts

echo
printf 'passed %d, failed %d\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
