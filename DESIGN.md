<!-- Hallmark · macrostructure: guided-workbench · theme: paper-ink · genre: modern-minimal
pre-emit critique: P4 H4 E4 S5 R5 V4 · slop test: pass -->
# EVIDEX design system

## Design context

EVIDEX Next is a working evidence-acquisition application for ordinary users,
not a promotional landing page. Its real material is an authorized Telegram
connection, a five-step form, a live job state, saved case files and a read-only
message viewer. No customer counts, endorsements or outcome claims are invented.

Preserve the two languages, all routes and form IDs, login prompts, cancellation,
session ownership, acquisition, export and hash behavior. Visual work belongs in
`evidex_next.css`, the existing HTML and the translation catalog. Do not rewrite
the Telegram engine as a design change.

## Durable preview block

- Genre: modern-minimal, calm and utilitarian.
- Macrostructure: guided workbench; inputs occupy the left panel, job actions and live state the right; a full-width activity log sits below both,
  then a separate saved-evidence shelf. No marketing hero/feature/CTA sequence.
- Theme: Paper & Ink (Kertas & Dakwat), a custom application theme informed by
  the restrained paper surfaces of Hallmark's Ink reference.
- Typography: Georgia/Times system serif for the page and step titles;
  Segoe UI/system sans for fields, labels and actions; system mono for logs only.
  No remote font dependency.
- Palette: warm off-white paper, neutral dark ink and a forest-green action/state
  accent. Colors are declared as OKLCH tokens in `:root` only.
- Key decisions: content-sized single-line actions; ordinary labels; no tracked
  capital eyebrows; hairline separation; flat surfaces; no resting shadows;
  content-only generated guide images in plain figures; existing mockups retained
  as archive files but never selected by the active guide.
- Slop-test outcome: pass for the user-supplied design contract. Chromium
  covered BM/English at 320, 375, 414, 768 and 1280px across 13 application/guide
  states per combination; no overflow, wrapped/clipped controls, language scroll
  jumps or JavaScript errors. Upstream mechanical floor: 0 FAIL, 0 REFLEX, 0 WARN
  in separate source and live-URL rendered checks. This is application-scope
  verification, not a claim about every unrelated landing-page rule upstream.

## Locked disciplines

1. Use named `--color-*` and `--font-*` tokens for every color and font declaration.
   Add a missing token to `:root`; never patch a literal color into a component.
2. Keep `overflow-x: clip` on html and body. Use `minmax(0, 1fr)` in image grids.
   Headings wrap with `overflow-wrap: anywhere` and `min-width: 0`.
3. Check 320, 375, 414 and 768px in both languages, including all wizard pages,
   the code/password prompt, completion, guide and message viewer. Controls may
   move to another row; their own clickable text may not wrap or be clipped.
4. No fake browser bars, phone frames, window dots or IDE chrome. Guide pictures
   depict content objects, not counterfeit interfaces. Real screenshots, if added,
   belong in a plain figure with an honest caption and no recreated device frame.
5. Keep visible keyboard focus and reduced-motion behavior. Language changes must
   preserve input values and must not scroll the page.
6. Any metric shown must come from the live job or a clearly labelled test fixture.
   Do not imply that hashes prove authorship, truth or court admissibility.
7. Before shipping, score Philosophy, Hierarchy, Execution, Specificity, Restraint
   and Variety from 1–5. Revise anything below 3 and stamp the design artifacts.
8. Preserve source files, routes and original evidence. Do not delete an old tool,
   asset or component tree as part of a visual redesign.

## Verification commands

```bash
python3 -m unittest discover -s tests -v
node tests/test_next_ui.cjs
```

The optional full-browser sweep is in `tests/test_design_render.cjs`. It uses a
local mock Telegram fixture, never real credentials. Its browser dependencies are
QA-only and are not required to install or run EVIDEX. The upstream Hallmark
mechanical floor checker is also run where its source and Chromium are available.

Source contract: the user's supplied Anti-AI-Slop Design Architect instructions.
Reference: https://github.com/Nutlope/hallmark . The current upstream skill differs
from the pasted version; the user's explicit brief takes precedence. No Hallmark
skill has been installed into or replaced in this repository.

## Pre-emit critique

| Axis | Score | Basis |
| --- | --- | --- |
| Philosophy | 4/5 | Task-first application; no promotional proof invented |
| Hierarchy | 4/5 | Left inputs, right job controls, full-width activity log and results shelf |
| Execution | 4/5 | Browser states, focus, contrast and narrow controls verified |
| Specificity | 5/5 | Real EVIDEX account, acquisition and evidence-file workflow |
| Restraint | 5/5 | Locked palette, local fonts, flat surfaces, no ornamental chrome |
| Variety | 4/5 | Form, state, evidence shelf and figure-led guide have distinct roles |

The scores are a design self-review, not product performance metrics.

## User-contract gate record

Every question below was answered **No** before handoff.

| Gate | Prohibited condition |
| --- | --- |
| 36 | Horizontal overflow in any tested viewport/state |
| 56 | Invented metrics, testimonials, logos or case-study counts |
| 57 | Fake browser, device, IDE or code-window frames in active output |
| 58 | Color/font literals bypassing the root tokens |
| 59 | Two-line or clipped button/link/summary text at mobile widths |
| 61 | Bare fraction tracks in image-bearing grids |
| 62 | Missing root overflow-x clip or root overflow-x hidden |
| 63 | Display heads missing safe wrapping or min-width reset |
| 64 | Multi-column dialog heads retained on mobile |
| 65 | Language-switch page scroll jumps; no radio-tab pattern is used |
| 66 | Hanging tag-left/heading-right section headers |

The full application test suite passed 62 tests. The UI-script harness passed
both languages, guide navigation, wizard validation and text-only message
rendering. `tests/test_design_render.cjs` uses mock Telegram responses and real
Chromium; no live login is needed. Original guide files remain in the repository
for compatibility but are absent from the active guide catalog.

## Local layout preview

Requested rework: form fields on the left; test, navigation, start and cancel in
the right control panel; an always-visible activity log below the work area.
On mobile these follow the same reading order in one column. Start retains its
association with the existing profile form. Backend and evidence behavior are unchanged.

The optional custom evidence-name field is initially blank, labelled in both
languages and limited to 120 characters. It uses existing form tokens and stays above the wizard, visible from the first step. New acquisitions include an Excel viewing copy; no old
export is modified.

## Version 0.2.2 usability update

Custom result naming is visible above every wizard step. Result management has
separate, plainly labelled delete-files and clear-history actions. Both ask for
confirmation; deletion affects only the validated selected case, while clearing
history writes a separate index and keeps evidence unchanged. Actions are blocked
during acquisition. The six illustrated tutorial pages now have two short
instructions each in Malay and English. Theme and typography remain Paper & Ink;
self-review remains P4 H4 E4 S5 R5 V4.

## Version 0.2.3 confirmation dialogs

File deletion and history clearing use an in-page modal dialog rather than
browser confirm popups. The dialog uses the existing palette, font and button
tokens, labels the action and consequences, and shows the selected case as
literal text. Cancel receives initial focus; Escape cancels; no request is sent
until explicit acceptance. Native dialog semantics contain keyboard focus and
restore it to the launching control. Both languages and narrow screens retain
single-line controls. Self-review: P4 H4 E4 S5 R5 V4.

Saved-result actions share one wrapping row: view messages, open folder, refresh,
delete selected files and clear history. Buttons retain their existing sizing;
on narrow screens they wrap as whole controls.
