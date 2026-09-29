# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root -- the glossary: canonical terms and the words to avoid.
- **`docs/adr/DESIGN_DECISIONS.md`** -- the decision log. Decisions are numbered by session (1.1 ... 8.6) in
  tables of decision + consequence; read the ones that touch the area you work in.
- **`docs/adr/DATA_MODEL_SPEC.md`** -- the authoritative data-model spec (sections cite decisions as "(7.10)").
- **`docs/adr/HANDOFF.md`** -- current state and where to resume; **`docs/adr/IMPLEMENTATION_PLAN_0.6.md`** -- phased plan.

## File structure

Single-context repo:

    /
    +-- CONTEXT.md
    +-- docs/adr/
    |   +-- DESIGN_DECISIONS.md          <- numbered decision log (one row per decision)
    |   +-- DATA_MODEL_SPEC.md
    |   +-- IMPLEMENTATION_PLAN_0.6.md
    |   +-- HANDOFF.md
    +-- src/ (backend, frontend, py_modules), grasshopper_userobjects_src/

This repo does **not** use one file per ADR (`docs/adr/0001-slug.md`). A new decision is a new row in
`DESIGN_DECISIONS.md` with the next number of the current session section; the spec cites it by number.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test
name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal -- either you're inventing language
the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag decision conflicts

If your output contradicts a recorded decision, surface it explicitly rather than silently overriding:

> _Contradicts decision 7.10 (the frame) -- but worth reopening because..._
