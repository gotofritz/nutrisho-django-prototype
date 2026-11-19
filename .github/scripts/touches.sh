#!/usr/bin/env bash
# Prints `<name>=true` when the commits from $BASE to $GITHUB_SHA change a file
# that `grep -E <args>` selects, and `<name>=false` when they do not. Each
# workflow's `changes` job appends it to $GITHUB_OUTPUT, and its other jobs run
# only on `true` (#145, #162). It prints the whole line itself so that a failure
# fails the step, which `echo "name=$(...)"` would hide.
#
# The path test sits on the jobs, not on the workflow's `on:` triggers: a
# workflow that a path filter skips never reports, so a required check would
# wait for it for ever, while a job skipped by its own condition counts as
# passed.
#
# With nothing to compare with (a schedule, a manual run, a new branch, a
# force push whose old commit is gone), it prints `true`: run everything.
#
#   touches.sh server -v '^extension/'   # a file outside extension/
#   touches.sh extension '^extension/'   # a file inside it
set -euo pipefail

name="$1"
shift

if [[ -z "${BASE:-}" ]] || ! git cat-file -e "$BASE^{commit}" 2>/dev/null; then
  echo "$name=true"
  exit 0
fi

# Collected first: `grep -q` stops at the first match, and a `git diff` cut off
# by it would fail the pipeline.
files=$(git diff --name-only "$BASE" "$GITHUB_SHA")
if grep -qE "$@" <<<"$files"; then
  echo "$name=true"
else
  echo "$name=false"
fi
