<!-- Hallmark · macrostructure: guided-workbench · theme: paper-ink · genre: modern-minimal
pre-emit critique: P4 H4 E4 S5 R5 V4 · slop test: pass -->
# EVIDEX development guidance

For UI work, read `DESIGN.md` first. Apply the user-provided Hallmark disciplines
to the existing EVIDEX Next front end; retain its two languages and working IDs.
Use the tokens in `evidex_next.css`, never component-local color/font literals.

Do not change Telegram connection policies, account/session selection, evidence
acquisition or export/integrity behavior to make a visual change. Preserve old
entry points and assets. Never invent product metrics, reviews or legal claims.

Verify both languages at 320/375/414/768px, including dialogs and login states.
Do not report a rendered check as passed when only source checks were possible.
Update the durable preview block and six-axis critique in `DESIGN.md` when the
visual system changes. Keep credentials and session contents out of logs/tests.
