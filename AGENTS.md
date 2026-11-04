# AGENTS.md

Guidance for coding agents working in this repository.

## Standing rules

- The maintainer makes every commit, push and production step. Do not stage, commit, push or run anything against
  production; leave changes in the working tree and give the commands. Commit messages stay inline in the command.
- ASCII only in code and scripts, no emoji. In docs, write dashes as `--` and `---`. Icons come from `lucide-react`.
- No names of people or accounts in committed files; refer to roles. The legal pages and the author line of the
  Grasshopper user objects are the exceptions.
- Packages must be about two weeks old: no dependency, action or lockfile entry younger than about 14 days.
- In user-facing text a single building component is an "element", and a recorded state is a "version".,e .
- Several docs and sources use CRLF. Keep the line ending of the file you edit.
- The root `README.md` states rules plainly, without decision references. Those belong in `docs/adr/`.
- The decision log `docs/adr/DESIGN_DECISIONS.md` is append-only: amend a row with an "Amended ..." sentence.

## Agent skills

### Issue tracker

GitHub Issues on `digitaldesignunit/csc` via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`); category labels (`bug`, `enhancement`, `frontend`, `backend`, `grasshopper-interface`, ...) stay as they are. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root, decisions as one numbered log in `docs/adr/DESIGN_DECISIONS.md`. See `docs/agents/domain.md`.
