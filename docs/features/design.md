# Design (`static/css/style.css`, `static/css/print.css`)

The site looks like an old illustrated children's book (#76): a lot of paper, a
serif text face, small-capital labels, no boxes or frames, and the occasional
loose ink-and-watercolour plate. The one exception is the recipe sheet, which
keeps the look it has when printed, because the site is the tools for writing in
that sheet.

## Rules

- Plain CSS, no framework and no build step. Most of it styles elements, so a
  template needs few classes. A Tailwind-style utility class styles nothing, and
  `tests/recipes/test_site_design.py` refuses one.
- No borders around regions. Space and type separate things. A field is a line
  to write on (a bottom border only), except on the recipe sheet, where fields
  keep their full edge.
- Buttons are small-capital words. The main action of a form sits on a
  sunflower wash with an uneven edge (`--wash-radius`), like paint, not a pill.
- Delete and errors are `--smock-red`; nothing else is red.
- Delete sits apart from the everyday actions: only in the recipe page's
  margin, behind a confirmation panel, never on the contents page (#75). It
  moves the recipe to the trash; the next page carries an ink toast at the
  bottom of the window with Undo, and the Trash page (in the site header)
  restores or deletes for good.
- Anything that only makes sense on screen carries `no-print`.

## Palette

The tokens are on `:root` in `style.css`.

| Token | Colour | Use |
|---|---|---|
| `--paper` | `#fbf8f1` | page background |
| `--ink` | `#2e2a24` | text |
| `--pencil` | `#5f574a` | hints, captions, blurbs (6.6:1 on paper) |
| `--marmalade` | `#9a4f10` | links on hover, labels, the current page |
| `--sunflower-wash` | `#f8d779` | the main button's wash |
| `--honey-wash` | `#fcebc0` | open panels, hovered buttons, selected rows in the staff tools |
| `--orange-wash` | `#f2a65a` | focus rings |
| `--smock-red` | `#9a3b28` | delete and errors (6.5:1 on paper) |
| `--color-field-border` | `#7a7062` | field edges, 4.6:1 on paper (WCAG 1.4.11) |

The main colour sits between orange and sunflower yellow. Text never goes on a
wash darker than `--sunflower-wash`.

## Type

- Libre Caslon Text: everything outside the sheet.
- IM Fell English SC: labels, buttons, the site navigation, headings of small
  sections.
- The recipe sheet keeps its own: Lobster for the title, Verdana at 20px for the
  text, Inconsolata for quantities.

All are self-hosted; see `browser-code-and-csp.md`.

## Pages

- Site header (`partials/_site_header.html`): the name, a search box and the
  site navigation, on every signed-in page. Ingredients and Cuisines appear
  for staff only. The current page's link has `aria-current="page"`.
- Recipe list (`home.html`): a book's contents page. Each entry is the name,
  a dotted leader, then the cuisine and servings, with the blurb below. The
  list is an `<ol>` numbered in Roman numerals that continue across pages
  (`start` is the page's first index). The search form reads as a sentence.
- Recipe page (`partials/_recipe_content.html`): the sheet in `<main>`, the
  tools in an `<aside>` margin beside it. Previous and next are quiet arrows
  fixed half way down either edge of the window, like turning a page; All
  recipes sits at the foot. Below 1000px the margin goes under the sheet and
  previous and next join All recipes at the foot, with their labels.
- Login (`registration/login.html`): a spread, with the lineout plate on one
  side and the name and form on the other. The copyright sits under the plate
  where a plate's caption would.
- Staff tools: the Miller columns, without frames; the column headers stick.

## Plates

A plate is a loose ink-and-watercolour drawing with a lot of white around it,
saved as `.webp` under `static/img/` on a white or transparent background. It is
shown with `mix-blend-mode: multiply`, so its white turns into the paper colour.
Give it an `alt` that describes the drawing, and its `width` and `height`.

## Print

`print.css` hides every `no-print` element and the margin, drops the sheet's
shadow and prints the sheet on white. A printed recipe looks as it did before
the redesign.
