# Steps

## Step Titles (`Step.step_title`)

Scraped recipes bury the heading of a step in the step itself — `<u>RAGÚ</u>:
Sauté the beef`, or `FOR THE STOCK: soak the kombu`. That heading is structure,
so it lives in its own optional field and the templates render it underlined
with a colon after it — the shape the scraped text wrote by hand — while the
colon itself stays outside `.step-title`, being punctuation rather than heading.
A step without a title renders exactly as it did before. Titles carry **no markup**: the `<u>` was
a wrapper around the heading, never part of it, so `_step_display.html` escapes
the title outright while `step_text` still goes through `safe_step_html`.

Titles are entered by hand in the step editor. Legacy steps had their
headings split off once by a backfill that has since been deleted (#56);
nothing splits or un-shouts a title at import or save time, because deciding
that a colon introduces a heading is a judgement about legacy data, not a rule.

## Merging, Splitting and Bulk-Deleting Steps (`recipes/utils/step_text.py`)

Every displayed step carries a checkbox (`.step-select`, posting `step_ids`).
Checking one reveals the steps panel above the list — count, Merge, Delete,
Cancel — the same hidden-until-checked pattern as the ingredient reassign
panel; Merge stays disabled below two. The panel, any error and the `<ol>` live
in `_steps_block.html` (`#steps-block`), which every multi-row step action
re-renders whole; move up/down still swap only `#steps-list`.

- **Bulk delete** removes the checked steps through
  `remove_many_and_compact`, closing every gap at once.
- **Merge** appends the checked steps, however far apart, onto the one
  **highest up the page**, one space apart (`join_step_texts`). That step
  wins: it keeps its title and other fields; the others' titles go. The
  result is validated through `StepForm`, so an over-long merge answers 422
  and writes nothing rather than truncating.
- **Split at cursor** is a button in the edit form of a saved step. It posts
  the form as typed plus `split_at`, the cursor offset in code points (computed
  by `app.js` from the button's `data-split-at`; the server folds CRLF to LF so offsets match the
  textarea). `split_step_text` moves a cursor inside a word back to that word's
  start and refuses — 422, the form re-rendered with a message — when either
  half would be blank, i.e. the cursor is not after the first word and before
  the last. The head keeps the title; the tail becomes an untitled step right
  below. The form targets its own row, so success answers with `HX-Retarget`
  onto `#steps-block`. Inline tags cut by a split are left to the render-time
  sanitizer, which balances them.

Selections are posted with the request, never stored; a stale or foreign id is
ignored, so a merge or delete that matches nothing answers 422.

## Sequencing (`recipes/utils/sequencing.py`)

All `index_in_sequence` mutations go through shared, transactional helpers:
`insert_at_index` (create at a DOM position), `remove_and_compact`
(delete + close the gap), `remove_many_and_compact` (delete several + close
every gap, keeping the sequence's base), `move_in_sequence` (swap with a neighbour via a
`-1` sentinel for SQLite's per-statement unique checks). Entity views must
not reimplement index arithmetic.
