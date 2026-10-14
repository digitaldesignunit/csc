# Contributing

Thank you for helping with the Catalog of Second Chances (CSC). Everyone taking part follows the
[Code of Conduct](CODE_OF_CONDUCT.md). Security problems are not reported as issues; see [SECURITY.md](SECURITY.md).

## Bug reports and requests

- **Open a GitHub Issue** with a clear title and description: what you did, what you expected, what happened.
- Name the **version**: the CSC version of the website or API (`/version`) and of the Grasshopper interface.
- Add a **screenshot** where it helps.
- For Grasshopper problems, attach a **minimal Rhino (.3dm) and Grasshopper (.gh / .ghx) file** that reproduces
  the issue.
- **Never post secrets:** remove your username and password from the `Session` component (and any Panel wired to
  it) before you share a .gh file, and never paste tokens, passwords, database addresses or dumps into an issue.
- Keep personal data of others out of screenshots and files.

## Pull requests

- Work on a branch; the maintainers use `v-<version>` branches for releases.
- Keep changes focused; add or update tests for what you change; CI must pass.
- Do not commit generated files, local configuration (`.env*`, `fastapi.ini`, `dbconfig.json`) or data.
- Use plain ASCII in code, scripts and docs, and do not name people or accounts in committed files (refer to
  roles instead).
- The domain language is in `CONTEXT.md`; design decisions are logged in `docs/adr/DESIGN_DECISIONS.md`. A change
  that alters a decision needs the maintainers' agreement first.

## Releases

Releases are made by the maintainers only; tags `v*` are protected.

- `VERSION` and the changelog section are set with `invoke bump-version <version>`; `.zenodo.json` follows with
  `invoke zenodo`.
- Pushing the tag `v<version>` on `main` runs CI, builds the three bundles (backend, frontend, Grasshopper
  interface), publishes the GitHub release and asks for approval before the deploy.
- The Grasshopper bundle takes its files from `grasshopper_release/`:
  - the interface file *DDU_CSC_GrasshopperInterface_<version>.gh* (the newest one not newer than the release is
    shipped, so add a new file only when the interface changed);
  - the examples *DDU_CSC_GrasshopperInterface_Example_<NN>.gh*;
  - the UserObjects from `grasshopper_userobjects/` and the shared library `grasshopper_lib/csc_gh/`.
