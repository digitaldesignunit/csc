# Implementation plan --- CSC 0.5.1.0 and 0.6.0.0

**Status:** draft 3, 2026-09-30 --- accepted by the user with the changes in section 5; P0--P3 done (2026-10-02). Implements `docs/adr/DATA_MODEL_SPEC.md` (draft 5) and the
decisions in `docs/adr/DESIGN_DECISIONS.md` (1.1--8.30). Terms follow `CONTEXT.md`.
**Branches:** P0 on `v-0.5.1.0`; P1--P12 on `v-0.6.0.0`, each phase on its own `v-0.6.0.0-P<n>` branch (P2b, P3, P4, ...).
**Phase order changed 2026-10-05 (decision 8.103):** after P8 come P9 in-place state and batches (new), P10 exports
(now before the cutover), P11 UI revision (called "P7b" in 8.102 and the UI / UX review), P12 cutover (formerly P9).
**Sizes** are relative (S < M < L < XL), not durations.

---

## 1. How the work is cut

- **Vertical phases.** Each phase lands backend + tests + the web UI it needs, so the branch
  always runs end-to-end against a migrated local database. The one exception is P2, where the
  data shape changes under every screen at once: P2 includes a read-only frontend catch-up.
- **Data first.** Migrations (P2) come right after the models (P1): every later phase develops
  and tests against the real 701 snapshots in migrated form, not against hand-made fixtures. The
  spec's per-dataset counts (section 8.1 step tables) are test oracles.
- **Pure functions first inside each phase.** Everything the spec calls a derivation (section 4),
  every predicate (visibility, permission, transitions, freeze, inheritance) is a pure function
  in `apps/catalog/` with unit tests and no database; routes are thin.
- **Tests green before the next step.** Every phase ends with a short review by the user;
  the user commits.

## 2. Test strategy

**Where tests run (decision 8.114, 2026-10-05):** CI runs only `tests/api`, the frontend, the deploy
script and the wheel check, on pull requests to `main` and releases; everything else runs locally by tier (changed
paths while working, one full parallel run per hand-off, no rerun by the review on an unchanged tree, one full run
including `slow` before every release).

| layer | what | how |
|---|---|---|
| unit | vocab, models, derivations (section 4), predicates (section 3.6, section 7.0, I15, I21), migration mapping functions | pytest, no DB --- the bulk of the tests |
| route | every route's permission row (section 7.0) x role, status transitions, 409 / 410 / 426 paths | pytest + `httpx.AsyncClient(ASGITransport)` (pattern already in `test_ghinterface_versions.py`) against a **throwaway `mongod`** started by a session fixture |
| invariants | section 5 as code: `scripts/db_maintenance/check_invariants.py` --- scans a whole database, reports every violation by invariant id | used by the migration rehearsal, by route tests (after each test module), and once against production after cutover |
| rehearsal | 260916 JSON dumps --> throwaway `mongod` --> section 8.1 in run order --> `check_invariants` --> per-dataset report vs. the spec's tables | one command, `invoke rehearse` (new task in `tasks.py`); rerun at every phase end and at cutover on the then-current dump |
| geometry | frame / shape class / proxies / complexity on real assets | tuning script over 260916 + `D:\01_PROJECT_WORKDATA\260916_CSC_ASSETS`; confusion tables reviewed by the user |
| frontend | no test framework today | `tsc --noEmit`, `eslint`, model codegen, and a scripted manual walkthrough per phase in the in-app browser (phone + desktop viewport) |

**Throwaway `mongod` (see section 5 Q1):** no MongoDB or Docker is installed locally, and the backend
uses PyMongo's `AsyncMongoClient`, which `mongomock` does not emulate. Recommended: install
**MongoDB Community Server** locally (same major version as the Atlas cluster) and add an own
pytest fixture (~30 lines, `tests/mongod.py`) that starts `mongod --dbpath <tmp> --port <free>`
from `PATH` or `MONGOD_BIN` and stops it after the session; route tests skip with a clear message
if no binary is found. The same install serves local backend development
(`MONGODB_URI=mongodb://localhost/csc06`) and the rehearsal. Rejected: `pymongo-inmemory` (works,
but last release March 2025 --- owning 30 lines beats a quiet dependency, as in 6.11); a database
on the Atlas cluster (network-bound, slow, shared with production).

---

## 2b. P0 --- 0.5.1.0 on `v-0.5.1.0` --- **done, released 2026-09-28** --- size M

Independent of the data model; ships first so a runtime problem is never confused with a
data-model one (6.12). User: "the pre-work" --- everything 0.6 builds on that does not change the
data model, **including a full local test environment** (item 0).

0. **Local test environment** --- MongoDB Community Server installed locally (user step); own
   pytest fixture `tests/mongod.py` starting a throwaway `mongod`; `app` / `client` fixtures that
   build the FastAPI app against it with temp storage dirs and test env vars; a first route test
   suite (auth, identities list / detail, snapshots, the header middleware); `invoke test` and
   `invoke dev-backend` (local backend on `mongodb://localhost`, optionally seeded from a local
   dump via `invoke seed --dump 260916`). README section "Local development and tests".

1. **Python 3.13** --- new venv; `requirements.txt` + `constraints.txt` with the glibc-2.17 ceiling
   and its reason (`numpy<2.3`, `scipy<1.17`, `scikit-learn<1.8`, `robust-laplacian<1.1`);
   `csc_env.yml`, README install + cron lines (`python3.9` --> `python3.13`). Existing test suite
   green on 3.13 locally, then on the server.
2. **Client header, logging only** (section 7.4, 6.7) --- FastAPI middleware logs `X-CSC-Client` per
   request (missing --> `unknown`), never rejects. GH: header added in `auth_core.auth_header()` in
   `DDU_CSC_Session` (covers the authenticated calls) and in the unauthenticated calls
   (`CSC_Update`, anonymous fetches); `gh-userobjects/0.5.1.0`. Web: the `/api/backend` proxy
   sets `web/0.5.1.0`. UserObjects shipped through `CSC_Update`.
3a. **Releases and deployment** (decision 8.5): `VERSION` + `invoke bump-version`,
   `/version`, CI / release / deploy workflows, `csc_release_deploy.sh` (releases
   dir, `current` symlink, rollback), GH updates from the running release, fix of
   the GH download serving the frontend bundle. Server conversion per
   `uberspaceconfig/deployment/README.md`.
3. **Photo EXIF strip** (7.13, section 3.5) --- `snapshot_images.py` drops GPS / owner / serial, keeps
   orientation, `DateTimeOriginal`, make / model; unit test with the 3 GPS-bearing asset photos;
   then step 14 (`migrate_strip_photo_gps.py`) on production.

**Done when:** `invoke test` runs unit + route tests against a local throwaway `mongod`;
deployed on Python 3.13; the log shows `gh-userobjects/0.5.1.0` and `web/0.5.1.0`; no stored
photo carries GPS. Uberspace steps are handed to the user as a terse checklist.

---

## 3. Phases of 0.6.0.0

### P1 --- Foundations --- size L

**Status: done**, committed by the user 2026-09-30; added since (8.12--8.18, working tree): I27,
I28, the I14 extension, `record_projection`, recall (8.18) --- 346 tests green, 1 skipped. Built:
`apps/catalog/vocab.py`, `documents.py` (all section 3 documents; one-document invariants as
validators naming their id), `permissions.py` (`can`, `can_see_component`, `can_see_record`),
`lifecycle.py` (I15 transitions, per-field PATCH rule of 8.3), `invariants.py` + the CLI
`scripts/db_maintenance/check_invariants.py` (all 27 ids + I3b; every data invariant already checks, the
rest are route-only); designs removed. The throwaway-`mongod` fixture came with 0.5.1.0. 312 tests
green --- 336 with the header enforcement (8.11: `CSC_MIN_CLIENT_VERSIONS`, unset = log only). First
run on the 0.5 dump lists exactly the P2 work (plus nulls, now in step 1c).

- `apps/catalog/vocab.py`: every controlled list of spec section 2 (original function, shape class,
  primitives, fit methods, evidence methods + tiers, quantities with unit / kind / scope /
  ranking, precisions, origin / exit kinds, statuses, roles, visibility, material seed).
- Pydantic v2 models for the new documents (section 3.1--section 3.7, section 3.2.1, section 3.2.3, section 3.3.1): identity with
  origin / exit / withdrawn, snapshot with status / supersession / capture / frame, proxy,
  evidence envelope (payloads come in P6), actor with accreditation, dataset, material, purge stub.
  `extra = "forbid"` where the spec says so.
- Pure predicates: `can(user, action, target)` over the section 7.0 table; `is_visible(user, identity,
  dataset)` (section 3.6); `transition_allowed(status, to, role)` (I15); `frozen_fields(doc)` (section 3.2.2,
  section 3.3.4).
- Client-header **enforcement** middleware with `CSC_MIN_CLIENT_VERSIONS` and the exempt paths (section 7.4).
- Test harness: throwaway `mongod` fixture, `check_invariants.py` (every id registered, checks
  filled in as their phase lands).
- Remove designs (7.11): routes, `/schema/design`, models; frontend `/designs` pages and
  components; GH design components move to the deprecated folder. (Archive script = step 13, P2.)

**Done when:** models validate hand-written examples of every section 3 document; predicate tables fully
covered; header tests (missing / old / exempt) pass.

### P2 --- Migrations and rehearsal --- size XL --- **done**
- Every section 8.1 script except the runner steps (5, 7, 8), in run order, each idempotent with
  `--dry-run` and its abort guards: 1, 1b, 1c, 9, 2, 11, 12, 3, 10, 10c, 10b, 6, 6c, 6d, 6b, 4, 9b,
  13, 14, 11b. Mapping logic as pure functions with unit tests (the step 10 table, the 37 / 5 / 1
  exit split, marker classification by position in 6c).
- `invoke rehearse`: load the newest dump (261001 since 2026-10-01), run all, `check_invariants`, print the per-dataset report.
- 6c needs the ddu source OBJs for marker labels; without them the position rule applies.
- **Read-only frontend catch-up:** regenerate models; lists, filters, detail page, viewer and
  map work on migrated data (`original_function`, `material` + class + trade name, `origin`,
  `exit` / circulation, `status`, `frame` read as `pca_frame` was, proxies instead of
  extrusions, no condition field); every write control hidden until its phase.

**Done when:** rehearsal runs clean except the invariants owned by later phases (frame, shape
class, proxies --- listed as expected-missing); the web app browses the migrated 260916 data.

### P2b --- Navigation shell --- size S --- **done** (built 2026-10-01)
- Decision 8.29 on its own branch: the shadcn/ui `Sidebar` primitive restyled for CSC; one entry
  list with visibility rules (signed out / user / moderator / admin); brand, groups, Recent,
  account menu; icon rail with tooltips, `Ctrl/Cmd+B`, cookie-remembered state, rail default
  768--1024 px, slide-in below 768 px; slim top bar (toggle, page title, page actions; Scan
  shortcut on phones); `Header.tsx` / `Sidebar.tsx` / `AppMenu.tsx` replaced.
- Moderation shows to admins only until P3 brings memberships to the session; P3 then adds the
  moderator rule, Users and invitations, Datasets and the queue badge; P7 adds Add component
  and Drafts.

**Done when:** every current page is reachable from the shell on desktop, tablet and phone;
keyboard and screen-reader navigation work; the collapsed state survives a reload without a
jump.

### P3 --- Datasets, permissions, lifecycle --- size L --- **done** (accepted 2026-10-02)
- Unpublished identity (8.9): derived state; creator + `moderator(D)` edit metadata and see it;
  evidence publish refused until the identity is published (I26); queue groups evidence with v0.
- `datasets` routes and memberships (section 3.6, section 7.7); `GET /users/me` with global role + roles per
  dataset (the frontend reads this; nothing role-related lives in the session token besides the
  global role).
- `require_dataset_role` on **every** write route (section 7.0); visibility on every read / list route;
  close the any-user file routes.
- Snapshot lifecycle (section 7.1): create-as-draft, submit (+ moderator publish / promote), publish,
  reject, recall (8.18), promote, withdraw / reinstate, draft delete, supersede (inherits `effective_from`);
  freeze (I21); one in flight (I3b); `PATCH /snapshots/{sid}` with per-field permission (8.3).
- Withdrawn = full record for D, tombstone outside (8.17): `record_projection` /
  `withdrawn_projection` on every read and file route; withdrawing the current snapshot falls back
  to the latest published one or null (I3b).
- Identity withdrawal, `duplicate_of`, purge + `purged_records` + 410 (section 3.1.4); `/id/{uuid}`
  resolver, API and frontend route (section 7.5); scanners accept UUID or URL.
  --- a piece the viewer cannot see shows "not public" + sign-in (anonymous) or "no access"
  (logged in) instead of a 404 (8.11).
- `RULES` gains `invite`, `revoke_invitation` (8.14) and splits `set_verification` into the
  recorder's `self_attest` and the reviewer's four-eyes act --- which the admin shortcut in `can`
  must not bypass (8.12, I27).
- Invitations (8.14): `invitations` collection, `POST/GET/DELETE /invitations`, `/auth/register`
  with code (email must match; counts as verified; grants dataset + roles),
  `CSC_OPEN_REGISTRATION_DOMAINS`; invite dialog in `/admin` and in the member editor.
- Member editor by email (8.20): `POST /datasets/{did}/members {email, roles}` --- add + notify an
  existing account, else invite (any domain); exact match for moderators, `GET /users/search`
  (prefix) for admins; `RULES` gains `search_users` (admin).
- Admin user list (8.21): memberships per account, URL-kept filters (text, dataset, dataset role,
  no dataset, global role, account state, invited); invitations tab. `GET /users` query params.
- Web: moderation queues (snapshots), `/admin` datasets + member / role editor, withdraw /
  duplicate dialogs, controls shown per `/users/me`.

**Done when:** a table-driven route test covers every section 7.0 row x {anonymous, user, contributor,
reviewer, moderator, other-dataset moderator, admin}.

### P4 --- Provenance, lineage, materials --- size M --- **built 2026-10-02 (backend + web), in review**
- `change_log` first (8.36, spec section 3.8, I30): one write helper used by every route that
  changes a record, retrofitted onto the P3 PATCH / lifecycle routes; `?as_of=`, `/changes`.
- Split / merge exit derived from published children (8.8): set on the child's first publish (needs
  `moderator` of child and parent datasets), `at` = earliest child `effective_from`, cleared when the last
  published child is withdrawn; tests for draft / rejected / withdrawn children and cross-dataset cuts.
- `origin` / `exit` / `past_cycles` routes (section 3.1.1, section 3.1.3, section 7.1): exit, undo, re-entry
  (server-set split / merge: first bullet); after re-entry the next snapshot defaults to the new
  `origin.at` (8.19).
- Lineage inheritance (section 3.1.2): copy-on-create, recursive propagation on parent PATCH, detach on
  child PATCH, re-inherit, merge unanimity (I17). The 0.6 `POST /identities` (identity + v0 draft)
  lands here because a cut needs it; P7 adds the new-component web form on top.
- `materials` collection + routes (section 2.10, section 7.7); `material_class` derivation + override (I25); delete / merge / retire (8.35).
- DIN SPEC 91484 / DGNB fields (8.38): origin `position_in_work`, `connection_types`,
  `detachability`, `construction_method`; identity `manufacturer`, `connection_features`,
  `material_separability`; section 2.11 vocabularies.
- Web: origin / exit forms and cards, lineage view with inherited markers, circulation filter,
  materials in `/admin`, "cut from..." entry point of the snapshot form (7.5). Built as: the
  provenance card (inherited markers, earlier cycles) with an edit dialog per inheritance unit;
  exit / undo / re-entry for moderator(D); "Cut a piece from it" on the component page (an
  authored box; the full snapshot form with photos and the tag-scan entry stays P7); the change
  history (members); `/admin/materials`. The circulation filter is the P2 one (in / out).

**Done when:** propagation tests over a 3-generation lineage incl. a merge; I16--I18, I25 checked by
`check_invariants` on the rehearsal DB.

### P5 --- Geometry runner --- size XL --- **built 2026-10-02 (backend + web), in review**
- `capture` block and fixture files (section 3.2.3, `SNAPSHOT_CAPTURE_DIR`); derivations never read
  markers / fixtures (I23).
- `main_geometry.py` (section 4.3) with stages frame --> shape_class --> proxies --> descriptors -->
  complexity --> previews; stages 1--2 synchronous on draft geometry writes and submit; `*_VERSION`
  skipping; replaces `main_descriptors_simple.py` and `main_previewgen.py` in cron.
- Frame (7.10, 8.1, 8.15): minimum-volume OBB, axis convention incl. the column rule, the valid
  frame closest to the stored axes (signs + ties within `max(2 %, 3 mm)`), stored as a transform ---
  stored coordinates never touched; unit tests for a square column, a cube and a flipped upload.
- Proxies (section 4.3, App. B): box, planar / linear prism, cylinder (in-house RANSAC, seeded), hull;
  residuals; deviation maps (16-bit PNG per face, spherical map for hull).
- Descriptors moved into the runner, frame-aligned, version bump. The four hull scores run in
  stage 1 with the frame (8.7); every stage stores `*_VERSION` + an input fingerprint and is stale
  on mismatch (test: override `shape_class` -> proxies, descriptors, complexity rerun).
- **HKS registered** (8.6): 3000-point even surface sample + point-cloud Laplacian for meshes,
  clouds and authored primitives; fixed seed; one fixed time grid in area-normalised units (derived
  once on 260916, then frozen); errors raise instead of `print` + `None`. Test: all 169 mesh
  assets of 260916 succeed (the probe's baseline: 169 / 169, rho 0.98 against merged meshes).
- **Tuning script**: shape class thresholds and complexity thresholds on 260916; confusion tables
  (complexity against the 71 authored `beyond_debris` ratings) --> user review --> thresholds frozen.
- Rehearsal now includes steps 5, 7, 8. Frame report: per dataset, how many frames changed axis
  order vs. 0.5 `pca_frame`.
- Web: viewer shows canonical vs. stored orientation, proxy + deviation-map overlay; GH-facing
  `frame` semantics unchanged for `ApplyFrame`.
- **Off the server (8.45, 8.51):** `main_geometry.py --remote <url>` pulls stale snapshots through
  admin-only routes, computes locally and uploads; the server refuses a result whose inputs changed
  (409) and recomputes the stamps itself.

Built as (decisions 8.46--8.51): `apps/catalog/{frame,shape_class,complexity,geometry_source,
geometry_stages,geometry_runner,remote_runner}.py`, `apps/catalog/proxies/` (`primitives`,
`sampling`, `robust`, `specs`, `registry`, `fit`, `deviation`, `png16`), `apps/descriptors/hks.py`
(grid derived once by `scripts/dev/derive_hks_grid.py` on the 238 mesh folders of 260916, 238 / 238
fitted), `main_geometry.py` (cron `geometry_cronjob.ini`, replaces the descriptor and preview
crons), `api/geometry_hooks.py` (stages 1--2 on every draft geometry write, submit, override and
function change; `POST /snapshots/{sid}/proxies/recompute`), `api/geometry_remote.py`, the deviation
map and proxy mesh routes, `derivation` stamps on the snapshot. The 0.5 `pca_frame` shim in
`read_models.py` is gone. Rehearsal (`invoke rehearse`) now runs steps 5, 7 and 8 and writes the
tuning tables (`scripts/dev/tune_geometry.py` --> `.dev/tuning_<dump>.txt`); `invoke dev-migrated`
derives frame, class, proxies and complexity. Web: orientation toggle (stored / canonical) and a
proxy overlay (outline, distance, normal deviation, points) in `ComponentViewer`, the maps decoded
in the browser (`lib/png16.ts`). The thresholds in `shape_class.py` and `complexity.py` are still
the initial guesses until the tables are signed off.

**Done when:** every rehearsed snapshot has frame, bbx, shape class, proxies, descriptors,
complexity; the user has signed off the tuning tables and the frame report. *(First half met on
dump 261001; the sign-off is open.)*

### P6 --- Evidence --- size XL --- **part 1 (backend) committed; part 2 (web) built 2026-10-03, in review**
- `component_evidence` + method registry (section 4.5) with the seven methods (A.1--A.4); payload
  validation incl. server-recomputed fields (rebound median / discard rule, core F/A, l/d class).
- Routes (section 7.2): create, bulk (all-or-nothing), lifecycle, supersede, verification (I22;
  8.12: recorder sets `self_attested`, four eyes for `reviewed` / `accredited`, I27, result edits
  reset it), attachments (one copy per record via hard link, sha256, add-only after publish, I24;
  8.13: download signed-in only, `gdpr` removal blanks the name, redaction worklist), methods /
  schema introspection with field descriptions.
- `resolve_snapshot_at` incl. archived cycles: a date inside a past exit --> re-entry gap is
  `after_exit` (8.19).
- Fold (section 4.4): both targets, `derived[]` results, verification factors, inheritance incl. merges,
  `outranked_evidence_ids`, propagation to inheriting children; timeline route.
- 8.16: evidence create on a withdrawn identity / after a terminal exit --> 409 (I28); one open
  correction per record (I14).
- Migrations 6b and 6d re-run with the real models in the rehearsal.
- Quantity rows `exposure_class`, `chloride_content`, `elastic_modulus`, `crack_width` (8.44) and
  the mapping columns per vocabulary row (QUDT unit, CERO / bSDD / IFC property; spec section 7.8)
  --- data for the P10 exports.
- Web: evidence form from the component page (7.1: fan-out, repeat-from-last, apply-to-several),
  "?" popovers from the backend descriptions, per-observation inspection photos (7.4), position
  picking on the viewer for meshes, point clouds and authored proxies, and the grid tool for
  rebound impact points and test-location layouts (8.43), the core-to-rebound pairing (8.42),
  evidence moderation + reviewer queue, properties card (range + n), condition badge (7.9),
  timeline.

Built as, part 1 (decisions 8.62--8.69): `apps/catalog/evidence/` (`payloads`, `specs`, `registry`,
`rebound`, `core`, `claims`, `projection`, `files`), `timeline.py` (`resolve_snapshot_at`, the merged
timeline), `properties.py` (the fold), `units.py`, `timeutil.py`; routes in `api/evidence.py`
(create, bulk, reads, queue, methods / quantities / schemas, properties, timeline),
`api/evidence_lifecycle.py` (lifecycle, supersede, verification, PATCH, DELETE),
`api/evidence_attachments.py`, `api/actors.py` (`POST /actors/redact`), `api/evidence_fold.py` (the
recompute, hooked into the snapshot lifecycle and the identity writes); quantity rows and mapping
columns in `vocab.py`; migration steps 6b / 6d through the registry and a new `fold` step;
`check_invariants` I8 and I11; `GET /identities/{id}/compose?include=evidence`; models regenerated
(`EvidenceModels.ts`, `EvidenceCreateModels.ts`). Part 2 (the web) is the bullet "Web" above.

Built as, part 2 (decisions 8.72--8.81, to confirm): route `/components/{id}/evidence/new`
(`?correct=<id>` for a correction) with `components/evidence/form/` (the form, per-method editors, the
request builder `state.ts`), the schema renderer `components/evidence/SchemaFields.tsx` and the "?"
`components/ui/help.tsx`, `lib/evidence/` (registry types and calls, schema helpers, layout hints, grid math, picking,
marks, display formats); the viewer gains `PickLayer`, `EvidenceMarks` and the `picking` / `marks` /
`fill` props (`components/components/ComponentViewer.tsx`) and the position picker dialog
(`PositionPickerDialog.tsx`: point, grid, test locations, edge warning); the component page gets
`ComponentEvidenceSection` (properties card, records, evidence timeline) and the condition badge;
`components/moderation/` gets `EvidenceLifecycleActions`, `VerificationPanel`, `EvidenceQueue`; the
moderation queue lists evidence, `/admin/review` is the verification queue. No backend change.

**Done when:** fold unit tests cover tier precedence, derived results, verification, inheritance
and merges; the phone walkthrough "scan --> add 3 rebound areas --> submit --> moderate --> verify" works.

### P7 --- Web completion --- size M --- **built 2026-10-03 (web + one backend removal), in review**
Decisions 7.5, 7.9, 8.16, 8.87; spec sections 3.3.2, 7.5, 7.6.
- One `SnapshotForm`, four modes (8.87 a): new component, cut (the P4 dialog folds in), record new
  state (only a changed shape; damage is evidence), correct (prefilled, geometry kept unless the
  size is entered again, same `effective_from`). Steps: details --> size (authored box) --> photos
  --> optional visual inspection (new component, through the P6 evidence form) --> submit (a
  moderator's submit also publishes and promotes). `/add-component` reopens on it; the 0.5 wizard
  and `lib/catalogCreate.ts` are deleted.
- Scan path (8.87 b): `/id/{uuid}` for an unknown id offers a signed-in contributor *New
  component* and *Cut from pieces* (scan the parent tags next); the scanners (identify, locate,
  transmit) lead there.
- Correct dialog (8.87 c): when the geometry changes, it lists the positioned evidence, each
  linked to its correction in the evidence form.
- Edit page `/components/[id]/edit`: the snapshot's mutable metadata (name, notes, location,
  colour) by the per-field rules of section 3.2.2.
- 0.5 leftovers (8.87 d): web consumers of removed fields gone (`type`, `extrusions`,
  `condition`, `consumed*`, `validated`, `iframe`, `pca_frame`); `/utility/compute-snapshot-
  orientation` and `orientation.py` removed; client header `web/0.6.0.0` (`package.json`).
- The full walkthrough (appendix A of this plan) passes on phone and desktop.

**Built as:** `components/snapshot/` (`SnapshotForm` with `DetailsStep`, `SizeStep`, `ParentTags`, `TagField`,
`PositionedEvidence`, `UnknownTag`, `UnknownTagLink`, `EditSnapshotForm`, `MetadataFields`), the pure parts and
their tests in `lib/snapshotForm.ts` / `.test.ts`; pages `/add-component`, `/components/{id}/snapshot/new`,
`/components/{id}/edit` and the `/id/{uuid}` unknown-tag branch; `initialMethod` on the evidence form for the
inspection hand-over. Deleted: `ComponentAddWizard`, `CatalogMetaSelect`, `lib/catalogCreate.ts`, `CutFromDialog`,
`orientation.py` with its route, models and test. Dev tooling: `invoke dev-migrated --test-accounts`, `NEXT_DIST_DIR`.
Decisions 8.88, 8.89 (to confirm); the results of the walkthrough are in the review report.

**Done when:** every item of appendix A works in the in-app browser on the migrated 261001 copy,
at phone and desktop width; tsc, eslint, `npm test` and the backend suite are green; no 0.5 field
is read or written by the web app.

### P8 --- GH bridge --- size L --- **part A built and confirmed (2026-10-03); part B built 2026-10-04 (to review); rewiring the definitions and exporting the UserObjects: the user**

**Rule (8.94):** touch only the components that must change --- because they break against the 0.6
API or data model, or because a settled decision asks for it (8.92, 7.8, `ApplyFrame`). P8 starts
with a read-only audit of every component (must change / works as is / drop), approved by the user
before any edit. Development components (save / export, release, dependencies) are reviewed only and
changed only when they would otherwise break, after asking. The frame rules (7.10, 8.52, 8.53) are
replicated in the client for offline use, kept in step with the server by a parity test on shared
test geometries. Rhino-document sync (bake, read back) goes through the D2P bridge.
- Header `gh-userobjects/0.6.0.0`; builders `Actor`, `Origin`, `IdentityMetadata`,
  `SnapshotMetadata` (7.6); `CreateComponentIdentity` / `CreateComponentSnapshot` with ~8 inputs,
  create-as-draft + submit, no PCA / reduction; robot-scan import writes `capture`;
  `ReinforcementLayout` + generic `AddEvidence` (7.8); `ApplyPCAFrame` --> `ApplyFrame`; inputs
  removed (`Type`, `Salvage*`, `Condition`, `Complexity`, `Assembly`, `Virtual`, `MarkerPoints`,
  `Reinforcements`); tooltips (dataset names) updated.
- Client performance, staying CPython (8.92): one `requests.Session` with keep-alive in
  `Session.py`; mesh upload through `Mesh.Vertices.ToFloatArray()` / `Mesh.Faces.ToIntArray()` and
  a numpy PLY writer; mesh download parsed with numpy, then the Rhino mesh build **measured** for a
  p90 reduced mesh (2.6 MB) and a median detailed mesh (12 MB) --- the number that decides a
  compiled helper later; two environments: `DDU_CSC` for the bridge (`requests` only) and a second
  one for the matchmaking tools (numpy, scipy, scikit-learn, ...), versions pinned in one place.
- Correcting a scanned version (8.91 a, 8.95 13): a supersede input on the snapshot components
  carries the new scan; `supersede` does not keep a scan's files for web corrections in 0.6.
- Step 1 (audit, done 2026-10-03, `.dev/p8-audit.md`) and its answers: decision 8.95 --- the
  component list, `Mesh.Reduce` kept for Preview / Reduced, centring as an input, environments
  `DDU_CSC` (requests, numpy) and `DDU_CSC_MATCH`, D2P plus a minimal built-in Bake / Sync on one
  user-text convention, `csc_placement`, authored-proxy fall-back in Fetch, FetchOriginalGeometry,
  Update with a local folder, `/auth/token` exempt from the version check, 0.6 schemas served,
  a `Capture` builder, the release definitions rewired.
- **Done when:** the DDU aggregation and robot-scan definitions run end-to-end against a local
  `invoke dev-migrated --test-accounts` backend reached from Rhino on the same machine (8.93); the
  `Session` component takes the server address, `CSC_Update` can read from a local folder.

**Built as, part A (decision 8.96, to confirm):** backend --- `/auth/token` exempt from the client check,
`/schema/create-identity` and `/schema/create-snapshot` serve the 0.6 bodies, the 0.5 request models are deleted.
Client --- `grasshopper_lib/` (`csc_ply`, `csc_build`, `csc_read`, `csc_frame`, `csc_rhino`, `csc_upload`, `embed`,
`envs.json`) embedded into the components by `invoke gh-embed`; Session (0.6.0.0 header, `Server` input, keep-alive
session, numpy PLY parse, swappable mesh build with Rhino's own importer as default, cache purge, 426 hint);
read path (FetchFilteredComponents, FilterComponents, DisassembleComponent, ApplyFrame, ComputeFrame,
FetchReducedGeometry / FetchOriginalGeometry with authored shapes, TransformComponent `csc_placement`); write path
(Actor, Origin, IdentityMetadata, SnapshotMetadata, Capture, CreateComponentIdentity / Snapshot, AddComponentIdentity /
Snapshot with submit, publish and supersede, ReinforcementLayout, AddEvidence); Update with `LocalFolder`; designs
dropped. Tests: `tests/grasshopper` (pure, Python 3.9 pins, headless Rhino 8), frame parity on 18 shared fixtures.
Left for part B and for the user: Bake / Sync / PassportToD2P / ReadFromD2P, the definitions, regenerating the
UserObjects in Rhino, the `/gh-interface` page.

**Built as, part B (decision 8.98, to confirm):** `grasshopper_lib/csc_convention.py` (the user-text convention, pure,
with the checks for everything read from a document) and `csc_doc.py` (bake a piece, scan the tags, read back); the four
components `BakeComponents` (`Level`, `WithPassport`), `SyncWithRhinoDoc`, `PassportToD2P` (IFC class -> D2P type id,
authored `Proxy` and capture `Marker` members, plane of the canonical piece) and the new `ReadFromD2P`. One piece in the
document is a group with one text label; the label plane now is the truth, so moving the group in Rhino moves the
piece in Grasshopper (`Q = P . F`); D2P commits its label without user text, so PassportToD2P puts the keys on the
members. Tests: pure (`test_convention.py`) and a headless Rhino 8 round trip on .NET 7 of both paths and across
(`test_rhino_doc.py`). `ViewCaptureToFile` has a new `Version:` line for its lean header. Not in the repository (binary
`.gh`, Rhino): the rewiring of the release / example / development definitions (`.dev/p8/rewire-list.md` lists each
change and canvas position), the in-Rhino checks of part B and the one export of every new and changed `.ghuser` /
`.xml` (`.dev/p8/in-rhino-checklist.md`, sections 7 to 9), and the web page `/gh-interface`.

### P8 part C --- shared library, declared outputs, fixes --- size M --- **next, before P9**

Decisions 8.111, 8.112; review findings of 2026-10-05 (viewport, .ghx I/O check). (1) `csc_gh` in Rhino's scripts
folder, version check, Update installs it, embed removed (8.111). (2) `OUTPUTS` declared, ensured from
`BeforeRunScript` (8.112): prototype on Origin and DisassembleComponent, checked by the user in Rhino, then all CSC
components. (3) Fixes: the blit writes float64 into `Point3d` (the self-check tests the same), a validity guard on
built meshes and proxies with a warning naming the identity, DisassembleComponent `Proxies` --> `Geometry`,
FetchTransmittedID `ComponentID` --> `IdentityID`, AddEvidence output `Created`; backend: prism profiles must be
simple polygons (422; migration strips the duplicated closing point and reports the 4 self-intersecting 0.5
profiles). **Done when:** pure tests green, the in-Rhino checklist of part C passes, the user exports the
`.ghuser` files.

### P9 --- In-place state, batches, catalogue import --- size L --- **grilled 2026-10-05, next after P8**

Decisions 8.104--8.110 (grill and review of 2026-10-05); spec sections 2.1, 2.2, 2.6, 3.1.1, 3.1.3, 3.1.6, A.3, A.4; glossary
terms in place, planned origin, batch, draw, remaining, document. Source data: the gitignored `scraped_sources/`
(catalogue A, catalogue B; each with `manifest.csv`, cached pages, docs, images).
- **Backend.** `origin.planned`; `POST /identities/{id}/deinstall` and `/undo-deinstall`; exit from in place
  (`recycled` / `disposed` / `lost` only); circulation filter `active` / `in_place` / `deinstalled` / `exited`;
  v0 of an in-place piece starts at its survey date (8.104). Batches: derived `remaining` on the identity read, the
  409 guard at draw create and first publish, the server-set `split` at `remaining == 0` and its clearing on
  withdrawal (8.105). `archival_document` without summary (a document; out of the fold), `document.url` +
  `retrieved_at` on `archival_document` and `reinforcement_layout` (8.106). Quantity `steel_grade`; functions
  `IfcWindow`, `IfcDoor`, `IfcStair`, `IfcRailing`, `IfcDuctSegment` with labels and shape-class hints (8.107).
  No migration: a missing `planned` is false.
- **Web** (8.109). In-place badge on cards, page and map popup; the circulation filter values; "Planned" in the
  provenance and new-component forms; "Record deinstallation" / "Undo deinstallation" on the Provenance card; the
  batch line, "Draw pieces" (cut mode with a quantity, the batch's proxy copied, tag optional) and the 409 message;
  "Documents from the batch" on drawn children; the document form (optional value, `url`, `retrieved_at`) and the
  Document card (the host as an external link); `steel_grade` and the new functions through `GET /vocab`. No redesign (P11).
- **GH** (8.109, rule 8.94). `Origin`: `Planned` input; `DisassembleComponent`: `Planned`, `Remaining` outputs;
  `FilterComponents`: `in_place`; `AddEvidence` tooltips. The user exports the changed `.ghuser` files
  (`.dev/p9/` checklist).
- **Import** (8.108). Untracked in `.dev/import_external/`: scraper, parser (cached pages --> entries), IFC element
  reader (ifcopenshell, local tools environment only), planner (entries --> plan JSON + report: counts per dataset,
  skips with reasons, mismatches), runner (through the HTTP API; `--dry-run`; resumable by `attributes.import`).
  Datasets A and B (ids in the untracked import plan), private, the user's personal account as moderator and contributor
  (account mapping in an untracked `.dev/` file). Recycling hall: one identity per IFC element (about 733), deinstalled
  2022; everything else: batches in place with authored proxies or element-IFC meshes.

**Done when:**
1. Backend suite green with pure tests for every rule above and API tests for every new route; `check_invariants`
   clean on the migrated 261001 copy.
2. The web items work in the in-app browser at phone and desktop width; tsc, eslint, `npm test` green; appendix A
   lines 22--24 pass.
3. GH pure tests green; the `.ghuser` export by the user.
4. `plan` on `scraped_sources/` gives a report the user approves; `run` on `invoke dev-migrated` creates both
   datasets; spot checks pass (an aerated concrete wall batch: in place, box proxy, photos, documents; a recycling-hall IPE 300
   piece: deinstalled 2022, mesh, `steel_grade` S235, linked mine-level files; a catalogue B HEB batch split into length
   classes); a second run creates nothing.

**Handed to P10:** Annex V 1(h) only when deinstalled and not planned; batch `quantity` and `remaining` in JSON-LD
and PDF; a document's `url` and `retrieved_at` as links in JSON-LD and CERO.

### P10 --- Exports --- size M

Decisions 8.39, 8.44, 8.103; spec section 7.8. Additive: no data change (6.8); moved before the cutover by 8.103, so it
ships with 0.6.0.0.
- JSON-LD context `/context/v1.jsonld` and `?format=jsonld` on the component read, from the
  mapping columns (P6 adds them).
- CERO exporter (Turtle / JSON-LD): conservative bound per property, link back to the record.
- PDF passport summary with ReportLab (`/identities/{id}/export/pdf`) and a "Download passport
  (PDF)" button. First check: a ReportLab wheel within the glibc-2.17 ceiling for Python 3.13
  (`constraints.txt`); no system libraries.
- Visibility tests: public tier vs. members, as the component read.

**Checked before the build (8.116):** JSON-LD on `/identities/{id}/compose?format=jsonld`; the items handed from P9
(1(h) only when deinstalled and not planned, batch `quantity` / `remaining`, document links, "In place" in the PDF);
a `conservative` mapping column per quantity; CERO only for concrete and AAC (409 otherwise); `steel_grade` IFC
mapping where IFC 4.3 has one; exports through the passport's read path (people, ETags, `Vary`, 401 / 403); QR from
ReportLab, a bundled OFL font, preview image fallback; `@id` from `FRONTEND_URL`; `pyld` / `rdflib` dev-only.

**Done when:** the three exports of a ZirKuS beam and a cut piece validate (JSON-LD expands with
a standard processor, the CERO Turtle parses, the PDF opens); also an imported in-place batch (no 1(h), batch line)
and a recycling-hall piece (1(h) filled, CERO 409); a public viewer's PDF and JSON-LD show no person and no
member-only data.

### P11 --- UI revision --- size L --- **scope grilled 2026-10-06 (8.118), not started**

Called "P7b" in decision 8.102 and in the UI / UX review (`.dev/ui-review/`, wireframes accepted in principle).
Decisions 8.101 (M2), 8.102 (History card), 8.118 (style rule, Q1--Q12, scope). Style: the existing shadcn
components and the blue / magenta CI colours stay; spacing and secondary shades may change.
- **Stage 1, component page**: header strip with chips, banner, viewer with toolbar, facts card "The component" /
  "This state" without duplicates, Properties (Add evidence), Provenance, Photos and location, Evidence records,
  History card (8.102 List / Graph with layers; versions read-only; change history); one Actions menu, Reserve
  visible; desktop two columns.
- **Stage 2, finding and moderating**: Browse (phone cards, desktop 8 columns + picker, filter bar, one circulation
  switch, anonymous public tier), My work (`GET /snapshots?mine=1`), sidebar of 12 entries, one Scan page, one
  Moderation page with tabs and counts, the access notice instead of the silent redirect; the map at full width with
  one toolbar and colour by dataset / shape class / material / circulation with a legend (C-2); Analytics with the
  shared filter bar, one summary line, charts first, a Circulation chart (C-3).
- **Stage 3, the rest**: snapshot / evidence form steps and method order, Settings (own roles, no emoji) and
  Materials table, terminology pass and day-precision dates, home page with the two calls to action; the full footer
  only on public pages, a thin line in the app, none in forms, Imprint always reachable (C-4); the Grasshopper page
  rewritten: download card, installation, a component reference generated from the sources' signatures and OUTPUTS (C-5).
- Leftovers: the cut dataset default without a parent in the link, the in-place map popup on real data, undo
  deinstallation in the browser.

**Done when:** each stage reviewed and accepted by the user in the browser at phone and desktop width; appendix A
passes again; no horizontal page scroll at 375 px.

### P12 --- Cutover (formerly P9) --- size M

**Tooling before the cutover (2026-10-07):** `scripts/dev/serve_migrated.py` restores the capture fixture files
(step 6c copy from the asset folder's `meshes/<sid>/1`) into its temporary `SNAPSHOT_CAPTURE_DIR` on every start,
also when it serves an existing database again; today a restart leaves the fixtures 404 (found in the P11 stage 3
acceptance). Development only; production keeps its files in the real `SNAPSHOT_CAPTURE_DIR`.
**Geometry before the cutover (8.119):** deviation-map face assignment by surface normal and the sample sized to
the maps (about 3 points per cell, 50 000--300 000), with the #709 test; the cutover's geometry runner run (step 3)
then writes the new maps.
**Preparation follow-ups (8.121, logged, not yet sent):** `main_geometry.py --sweep` (default off; the production cron
sets it), the map distance to the assigned face's plane, the planar prism outline input capped at 50 000 (measure the
aerated concrete wall), and a planar accept check with a box fallback (8.121 d). On the server, the sweep is right because its
asset folder matches the production database.
**Geometry result cache (8.122 f, logged, not yet sent):** `main_geometry.py --cache-dir <dir>` stores every result of a
local run (result JSON, deviation maps, `preview.webp`), keyed by snapshot id, chosen PLY per mesh / cloud with its size,
stage versions and context; with `--remote <url> --cache-dir <dir>` a stale snapshot whose key matches
`GET /geometry/work/{sid}` is uploaded from the cache (no download, no computation), any other computed as today
(`GET /geometry/work` gains the file sizes if it lacks them). Before the day: one full local pass on the latest
rehearsal with `--all` (it measures the time a full pass takes), a refresh pass on the last rehearsal. The cache is filled by the same
commit that is tagged and deployed (stage versions and rules must match, else every key misses); a full quiet pass
takes about 14 min for 701 snapshots (Agg backend; 2026-10-08).
**Older versions (8.123, logged, not yet sent):** (a) an empty frozen `capture` field filled once in place by
`moderator(D)` (PATCH, change history); (b) I3 orders a correction at the first record of its `supersedes` chain, the
timeline shows it as that version corrected, a correction becomes current only when its predecessor was (`promote`
ignored otherwise), test: correct v0 while v1 is current; (c) "Edit details" with a version choice (`?snapshot=`) and
the fields `capture.notes`, `effective_from` and the empty capture fields.
**Mail (8.124, logged, not yet sent):** password reset (two routes, sign-in page link, `password_changed_at` checked
in `lookup_user_from_token`, also set by `change-password`); `mail_failed` per address with **Resend** in the
invitation and member editor UI; sending in a thread pool, one SMTP connection per bulk invitation; one escaped
template for the four mails (`[CSC]` subject prefix, footer with the reason and `/imprint`, no "do not reply");
`Reply-To` the acting moderator for invitation and member notice. Tests in dev mode (`SMTP_DEV_MODE`), incl. a
token issued before a password change refused and a reset for an unknown address answering 202.
**Private means private (8.125, logged, not yet sent):** (a) every direct `csc_assets` URL user (frontend image
config `next.config.ts`, `lib/utils.ts`, `csc_gh` and the GH components, exports) moves to the authenticated
`/snapshots/...` routes; the deployment examples (`uberspaceconfig/.bash_profile.example`,
`etc/services.d/fastapi.ini.example`) put the six `SNAPSHOT_*_DIR` under `~/csc_assets_private/`; a
`Require all denied` `.htaccess` for `~/html/csc_assets/`; (c) step 11b adds the global `moderators` only to datasets
created by step 11 (a test with a dataset created after the migration); (d) the map payload's `total` from the
visible points.
**Nobody publishes directly (8.120):** submitting never publishes, for any role; publishing is the separate publish
route from the queue, self-moderation allowed ("Own record" chip); the import submits, then publishes. Today the snapshot form sends
`submit?publish=1&promote=1` (`SnapshotForm.tsx:402`), so a moderator's or admin's submit publishes at once; the
evidence form (`EvidenceForm.tsx:354`, `EvidenceLifecycleActions.tsx:106`) and the GH upload (`csc_gh/upload.py`) do the same.
**Cutover day (8.122):** one day, the site offline throughout; no announcement. Order:
(i) pause both crons (`geometry_cronjob`, `geometrymaintenance_cronjob`), stop 0.5.1.0, take the dump and the asset
backup (step 1); (ii) rehearse locally on that dump (step 2) --- not clean: abort, restart 0.5.1.0, nothing to restore;
(iii) move the six `SNAPSHOT_*_DIR` folders from `~/html/csc_assets/` to `~/csc_assets_private/` (`mv`, same
volume), update the env, add the deny `.htaccess` (8.125 a); remove the global admin role of the `ddu_aggregations`
project lead (8.125 b); deploy 0.6 with `CSC_MIN_CLIENT_VERSIONS` set in the same deploy, section 8.1, `check_invariants`, designs archived
(steps 3, 4, 5); (iv) external catalogue import (step 3b); (v) geometry runner with the result cache (8.122 f), `main_geometry.py --remote <url> --cache-dir <dir> --all`
(without `--all` a run stops after 5 snapshots, `DEFAULT_LIMIT`), until `GET /geometry/stale` is empty, then the map
cache rebuilt once (steps 3 and 4d); (vi) checks 4b and 4c, and the mail test of 8.124 c (TU and an outside address, SPF / DKIM / DMARC pass, from the new
Uberspace mailbox); (vii) the user's old-client test on production (old Session
signs in, old `CSC_Update` installs the 0.6 UserObjects, the new one `csc_gh`; a non-exempt route answers 426);
(viii) the smoke list below; (ix) reopen, then re-enable the crons with the 0.6 lines (`--sweep`). Before the day the user
tests the old update path against the 0.6 dev backend with the minimum set.
**Rollback (8.122 c):** a failure from (iii) on that cannot be fixed the same day restores everything:
`mongorestore --drop` of the cutover dump, `csc_release_deploy.sh --rollback`, `rsync --delete` of the asset folders from
the backup of (i) into the old `~/html/csc_assets/` paths with the old env and without the deny `.htaccess`, restore
the project lead's admin role, restart 0.5.1.0 (crons stay paused until the new day). Reopening is the point of no return; after it,
fix forward with 0.6.0.x.
**Smoke list before reopening (8.122 e),** on production, ticked line by line; any failure blocks reopening:
1. `/health` answers; `/version` says 0.6.0.0; anonymous home and Browse load.
2. Anonymous: a public piece shows the public tier (no people); a non-public `/id/{uuid}` says "not public" with sign-in.
3. Signed in as the maintainer: sidebar, My work, Browse filtered by a dataset; a migrated ZIRKUS piece shows the History
   card, the proxy detail with the distance overlay, and its photos.
4. The external catalogue datasets are private: their pieces are visible signed in, not anonymously.
5. Moderation queue opens; `/admin/geometry` lists no failed stages, or only known ones.
6. Component map loads, colour-by switches.
7. Exports of a public piece: `compose?format=jsonld` and the PDF passport (4b covers the links).
8. Grasshopper with the 0.6 UserObjects: Session signs in, Fetch a piece, Bake it. Writes are covered by the import (iv).
9. Privacy (8.125): `curl` of a former `/csc_assets/snapshot_previews/<sid>.webp` URL answers 403 or 404; an external catalogue
   piece by id answers 401 anonymously; `/users` lists exactly two admin accounts.
1. Take production offline (stop 0.5.1.0, pause the crons); take the cutover dump + assets backup.
2. `invoke rehearse` on that dump --> clean report (the abort guards catch drift since 260916).
3. Deploy 0.6 backend + frontend; run section 8.1 on production in run order; `check_invariants`;
   rebuild the component-map cache (`main_component_map.py`: the cache ids changed with the 0.6
   filters).
   3b. Rights first (8.110 d; decided 2026-10-08, 8.128: no consent, so documents are linked only, `run.py --no-files`;
   photos imported with a `photo_credit` to the catalogue operator, datasets private): with the catalogue operators' written consent the files go along, otherwise
   import without photos and documents, citing them by `url` + `retrieved_at`. If the files go: build the hard links
   of 8.108 first or accept the size (the rehearsal copied 312 MB, one file per record; 8.115 f). Import the external catalogues (8.108): `.dev/import_external` `plan` --> the user reads the report -->
   `run` against production with the user's personal account (it already exists on production; no account is
   created at the cutover for the import); the second run creates nothing.
4. `CSC_MIN_CLIENT_VERSIONS` set to 0.6.0.0 in the deploy of step 3 (8.122 b); publish the bridge UserObjects via `CSC_Update`.
   4b. Exports (8.117 c): `curl` a public piece's `compose?format=jsonld` and check that `@context` and the PDF footer
   links say `https://` on the public API host (they come from the request URL behind the proxy).
   4d. Rebuild the map cache after the deploy: the points carry dataset / material / shape_class since P11 stage 2.
   4c. Client addresses (8.117 e): production uses `FASTAPI_URL=http://127.0.0.1:<port>` (else add the connecting and
   the server's own address to `CSC_TRUSTED_PROXIES`); check the peer address the backend sees from the Uberspace
   proxy; send a request through the public domain with a made-up `X-Forwarded-For` and confirm the web server
   receives two entries (the made-up one and the real address); two visitors do not share a limit (README).
5. Designs archived by step 13 (count verified).
6. After cutover: the other personal accounts created (the maintainer's exists already, step 3b) --> fill in the untracked `.dev/reattribute_06.json` --> step 11b
   re-attributes every `ddu` / `admin` record by the 8.24 mapping and adds the two moderators of
   every dataset (8.25); `ddu` and `admin` stay as the user- and admin-role test accounts with no
   records (8.22, 8.25); further memberships assigned in `/admin`.

### Backlog after P12 (0.6.0.x) --- logged 2026-10-08; RL2 + bulk submit before the cutover (8.127), the rest in 0.6.0.1

**0.6.0.2 (8.129--8.131, user 2026-10-09):** an operations release: bundle fix, `seed_materials` upsert, `shapely`
cap + `--only-binary`, `CSC_WORKERS` / `CSC_LOG_LEVEL` and one lock for the heavy crons, the public switch (piece +
dataset) and the notice, the "No scan" hint, the dry-run note, `crontab.example`. The items below that 8.129 does
not name stay for 0.6.0.3 or later.

**Reinforcement layouts** (review report 2026-10-08; workflow: GH builds the bars in the snapshot's stored
coordinates, `AddEvidence` uploads, the drawing is an attachment on the same record, added in the web):
- RL1 (user): several layouts per piece, e.g. one from the archival drawing and one from a covermeter / Ferroscan
  survey. Already possible: no uniqueness per method or snapshot; the fold ranks the scan (ndt) above the drawing
  (archival). To confirm in the web: the evidence card lists both, the viewer draws both.
- RL2 (user, **decided 8.127, before the cutover**): Grasshopper supplies geometry first and foremost; drop the `Submit` input of `AddEvidence`
  (and of `AddComponentIdentity` / `AddComponentSnapshot`), so everything from GH lands as a draft and is completed
  (files, checks) and submitted in the web. Coordinator: agree --- it matches 8.120, fixes the order problem of
  attaching files to a pending record, and keeps GH a geometry tool; it needs a **bulk submit** in My work (select
  drafts --> Submit), since robot-scan runs create many records at once (today My work has no bulk action).
  With it (8.127): an **Edit** action for evidence drafts (`?edit=<id>`, `PATCH`); today a saved draft can only be
  submitted or deleted.
- RL3 (user): colour-coding of bars in the web viewer, optional: by layout (one colour per record, default when more
  than one layout is shown) or by diameter (sequential scale), with a legend; toggle next to the overlay controls.
- RL4: a correction starts without attachments and its form hides the file field (`evidence_service.py:521`,
  `EvidenceForm.tsx:676`); carry the attachments over (hard link, as in the bulk upload) or allow files on the
  correction form.
- RL5: the migrated ZirKuS record (step 6d) has `document` null; filling title / date / reference needs a correction
  today; extend "fill once" (8.123 a) to empty `document` fields of a published evidence record.
- RL6: the GH `ReinforcementLayout` builder lacks `url` / `retrieved_at` of the drawing (8.106).
- RL9 (user 2026-10-10, 0.6.1.0 with RL6): `ReinforcementLayout` needs bar curves in the snapshot's stored
  coordinates (mm), but nothing converts bars drawn on a piece moved by `ApplyFrame` (canonical, centred) or
  `TransformComponent`; today the user must Orient World XY --> `Frame` or invert the transform by hand. Add an
  optional `ComponentPassport` input: when it carries a `csc_placement`, the component maps the curves back to stored
  coordinates (inverse of the placement) and takes `SnapshotID` from the passport (an explicit `SnapshotID` that
  disagrees is an error); a remark says which conversion ran. Also: refuse or warn when the document unit is not
  millimetres (scale by the unit factor), and say in the component description that a layout belongs to one
  version. Same handling for any later GH builder that takes positions on a piece (Ferroscan, 0.6.2).
- RL11 (user 2026-10-12, 0.6.1.0 phase C): GH cannot read reinforcement back (no component reads evidence; the
  API has `GET /identities/{id}/evidence?method=reinforcement_layout` and `GET /evidence/{id}`). New component
  `FetchReinforcementLayout`: input `ComponentPassport` (or `IdentityID` / `SnapshotID`), optional `Status` (default
  `published`, `all` adds the caller's drafts), optional `Pipes`; outputs one polyline per bar as a tree with one
  branch per layout record (newest first), `Diameter`, `Spec`, `Cover`, record id, basis and snapshot id per
  layout, and solid bars with `Pipes`. A passport `csc_placement` (Q, 8.98) moves the bars stored --> placed, the
  same transform `Fetch...Geometry` applies to the mesh; RL9 is the inverse on the way in. Layouts of another version
  than the passport's are listed with their snapshot id and a remark (their coordinates belong to that version).
- Units in GH (user 2026-10-12, later; 0.6.1.0 chose "no scaling"): every GH component uses stored millimetres
  1:1 as document units and the reinforcement components only warn in a non-mm document. One later task scales all
  of them by the document unit together (fetch / apply-frame / bake / reinforcement in and out), never some of them.
- RL10 (user 2026-10-10, 0.6.1.0): the evidence card never shows a layout's `accuracy_note` (only the form has it,
  `lib/evidence/layout.ts`). Show it in the card's unfolded details for signed-in viewers (with the basis, the
  document or instrument block); anonymous viewers do not get it (hidden in the web; whether the public tier of the
  API drops it too is decided with the build, 8.67 / 8.101).
- RL7: `position.kind` is `none` from GH and `region` from the web form for the same method; pick one.
- RL8: the steel grade stays inside the bars and never enters the fold; the spec's answer is a separate `rebar_spec`
  claim sharing the attachment (7.8), which no GH component builds.

**From the 8.128 review:** the photo credit is not in the exports (JSON-LD, PDF passport); `editValuesOf` and
`ComponentPhotosLocationCard` cast the snapshot to reach `photo_credit` although the generated type has it.

**IFC export** (user 2026-10-08; idea in `FUTURE.md`, BIM / IFC): a fourth export next to JSON-LD, CERO and the PDF
passport (P10, 8.116), e.g. `compose?format=ifc`: one `IfcElement` per piece with the IFC class of its original function
(the vocabulary already maps it), authored proxies as `IfcExtrudedAreaSolid`, meshes as `IfcTriangulatedFaceSet`,
canonical or stored placement, properties and identity fields as property sets through the existing IFC mapping
column (8.44, spec 7.8 / 10.4), public tier rules as for the other exports. Grill first: IFC4 or IFC4x3, single piece vs.
a selection, `ifcopenshell` on the server (wheels for Uberspace 7, glibc 2.17; `invoke check-server-wheels`) or a
plain STEP writer, and an optional GH path.

**Frontend toolchain** (2026-10-09, Next.js 16.4.0 upgrade before the cutover): `eslint-config-next` /
`@next/eslint-plugin-next` stay on 16.3.x, because 16.4 pulls `eslint-plugin-react-hooks` 7.1.1 (and a newer
`typescript-eslint`), whose rule reports 12 new errors "Cannot access refs during render" in existing code:
`ComponentMapPageClient.tsx` (8, the latest-ref pattern around line 196--233), `SnapshotForm.tsx` (3, around line 675),
`components/moderation/useDetails.ts` (1). Refactor those (refs written in effects or event handlers), then raise the
lint packages to 16.4. `npm audit --omit=dev`: 7 findings that predate the upgrade (high: undici, sharp,
brace-expansion, http-cache-semantics, source-map-js; moderate: ip-address, postcss-selector-parser); update the
dependencies that carry them and check the server build (Uberspace 7) still works.

**Component map: HKS as a basis** (user 2026-10-09): the map embeds only `radial_signature` and `scalars` today
(`MAP_BASES`); add the heat kernel signature (8.6, stored per snapshot by the descriptors stage) as a third basis,
selectable on the map page, with the cache cron building it; check how many published pieces carry an HKS (authored
pieces get one from their primitive) and how the PCA / UMAP layouts behave on it.

**Found on the cutover day (2026-10-09):**
- `seed_materials` (`catalog_common.py:231`) races when several gunicorn workers start on an empty `materials`
  collection (E11000 in the losing workers, gunicorn halts, "spawn error"); make it upsert or
  `insert_many(ordered=False)` ignoring duplicate keys, with a test that runs it twice concurrently.
- Server venv: `shapely` 2.2.0 ships only glibc 2.28 wheels, the deploy compiled it and failed; cap
  `shapely<=2.1.2` in `constraints.txt` and install with `--only-binary=:all:` in `csc_release_deploy.sh`, so the
  deploy matches `invoke check-server-wheels` and a missing wheel fails fast instead of compiling.
- `migrate_06.py --all --dry-run` aborts at step 10 because the 11a slug rename is not applied in memory; make the
  dry run carry the renames forward, or document that only the rehearsal checks the whole chain.
- The import saw 3 connection resets from the server mid-run (14:35:40); check `fastapi.log` for worker restarts or
  memory (4 workers with the geometry libraries) and consider `workers = 2`.
- Viewer: a piece without scan (authored proxy only) offers no overlay; say "No scan: overlays need a mesh or point
  cloud" instead of an empty menu.
- Frontend bundle (blocking for the next release): since 0.6.0.0 `app/gh-interface/page.tsx` reads
  `public/gh-interface` at run time, so Next's file tracing already puts `public/gh-interface` into the standalone
  output; `package_release.sh` then runs `cp -a "$fe/public" "$bundle/public"` into the existing folder and nests
  it as `public/public/`. Only the traced screenshots are served; `/logo/` and `/backgroundmeshes/` answer 404. Copy
  the contents (`mkdir -p "$bundle/public" && cp -a "$fe/public/." "$bundle/public/"`) and fail the packaging when
  `public/logo/ddu_logo_black.png` is missing from the bundle. Patched by hand on the server on 2026-10-09.
- Public switch (user 2026-10-09): the web app cannot set `is_public`; only `POST /identities` (Grasshopper input) and
  `PATCH /identities/{id}` can (moderator(D), or the creator while unpublished, 8.9). Add a "Public" switch to "Edit
  details", shown to whoever may PATCH, with a line on what anonymous visitors then see (public tier, 3.6, 8.101,
  8.13). Fix the "Not public" notice in `lib/componentDetail.ts`: in a `catalog` dataset every signed-in user sees
  the piece too, so name the dataset visibility instead of "only members ... and the moderators".

**Other review findings of 2026-10-07/08 (non-blocking):**
- Geometry cache (8.122 f, review note 2): a frame-only cut uploads the cached `descriptors` dict with the frame stamp,
  so the descriptors stage looks fresh by value although it never stamped; today only a comment in `_outcome`. Strip the
  descriptors-stage keys when `descriptors` is not among the uploaded stages.
- Planar outline (hang fix): the vertex limit counts the exterior ring only; holes of a section polygon are not counted.
  The wall test has a 60 s bound and could flake on a very slow machine.
- Evidence edit (8.127, note b): a moderator's edit that changes the performers of a self-attested record resets the
  verification to unverified without the form saying so; show a notice before saving.
- README: the `SMTP_REPLY_TO` sentence (about line 184) runs to about 120 characters in an 80-column paragraph.
- 0.6.0.2 review (note a): `identity_edit._write` logs the change before `replace_one`, so a piece the bulk public
  route reports as skipped (409) already has a change-log entry with the new flag (the single PATCH has the same
  order); log after the replace.
- 0.6.0.2 review (note b): `POST /datasets/{did}/public` validates each piece through the identity model; a stored
  identity that fails validation answers 422 after earlier pieces were written, without counts. Validate all first,
  or report written / skipped / failed counts.
- 0.6.0.2 deploy (2026-10-10, blocking for the next release): the GitHub deploy runs `~/csc/bin/csc_release_deploy.sh`,
  which `after_success` replaces with the release's copy only after a successful deploy; so a change to the deploy
  script takes effect one release late. The 0.6.0.2 run used the 0.6.0.1 script without `--only-binary`, built a new
  venv (constraints changed) and pip tried to compile the newest `numba` from source. Fix: after unpacking, re-exec
  the release's own `deploy/csc_release_deploy.sh` when it differs from the running one (guard against loops), and
  pin the transitive geometry stack in `constraints.txt` to the versions the server venv runs: `numba==0.67.0`,
  `llvmlite==0.49.0`, `pynndescent==0.6.0`, `umap-learn==0.5.12` (numpy stays `<=2.2.6`), so plain `pip` and
  `invoke check-server-wheels` resolve the same set. Worked around by hand: scripts fetched from the v0.6.0.2 tag.

**Earlier items:** the paired rebound not linked on the core record; `window.confirm` --> shadcn `AlertDialog`
(moderation delete, material delete); snapshot-scoped properties follow the version time order.

### Backlog 0.6.1.0 --- opened 2026-10-10 (user); items to grill before the build

0.6.1.0 is the next working release (user 2026-10-10); a 0.6.0.3+ only for a hotfix-worthy problem. So 0.6.1.0
also takes the open items of the 0.6.0.x list above, first the two deploy blockers (the deploy script's self-update
lag and the transitive geometry pins), since its own deploy depends on them.

**Scope decided (8.132--8.142, user 2026-10-10); build in phases, each through review:**
- **A, operations (first; "go" 2026-10-10):** the deploy re-execs the release's own script (guarded) and the
  transitive geometry pins (`numba==0.67.0`, `llvmlite==0.49.0`, `pynndescent==0.6.0`, `umap-learn==0.5.12`); 8.136
  (batched identity loads, `derivation_due` markers, nightly full check and `--sweep`); the projected snapshot joins
  of the list, map and row pipelines (Atlas traffic, below); the maintenance mode 8.137; `crontab.example` with the
  20-minute marked run, the nightly full run with `--sweep` and the daily map.
- **B, backend:** profile 8.133; user-created datasets with the review gate 8.139; RL4 / RL5 / RL7 (8.142), RL10;
  history endpoint and export 8.140 g / h; photo credit in the exports; the two 0.6.0.2 review notes; the
  evidence-edit notice.
- **C, Grasshopper (user's OK):** RL6, RL9, RL11 (`FetchReinforcementLayout`), the `Actor` `Me` input (8.133 f,
  amended).
- **D, web:** evidence forms 8.134 (with h); edge distance 8.135; preview and id chips 8.141; swimlane 8.140; RL3;
  HKS map basis and level 1 curve; provenance dialog gaps and `Actor.url`; privacy page; credits page (partner
  names, links and consent from the user).
- **E, mail templates (8.138 e as amended):** Jinja2 templates, HTML and text, the site's colour theme, no logo or
  image; the logo moved to `FUTURE.md` (user 2026-10-12).
- **F, toolchain:** lint refactor and lint packages 16.4; npm audit with a glibc 2.17 server build test.

**Atlas traffic (2026-10-10, at the front with the deploy fixes and 8.136):** since the cutover the primary's
network rose from near zero to about 1 MB/s with about 60 requests/s for hours (the geometry runner reading every
snapshot every 5 minutes, one identity round trip each), and stays at about 250 KB/s; the free tier (M0) throttles,
so every response carrying snapshot bodies slowed down (`/identities`: about 1.3 s per row, Browse about 8 s, while
`/version`, `/health/db` and `/identities/count` answer in 0.1 s). Besides 8.136: (a) the list, map and row
pipelines join the current snapshot projected to the fields a row reads (no `descriptors`, no inline `geometry`, no
proxies' deviation data), and `expand=current_snapshot` projects what the passport body uses; (b) a test pins the
projection (a row built from the projected join equals one built from the full document); (c) measure the bytes per
request before and after on a copy of the production data. If traffic stays near the M0 limits afterwards: decide
between a paid Atlas tier and a MongoDB on the server, with the measured numbers.

**Maintenance mode** (8.137, user 2026-10-10): `csc_maintenance.sh on | off | status`, the static 503 page in
`uberspaceconfig/html/maintenance/`; first verify the per-domain Apache folder on a test subdomain.

**Privacy notice and cookie notice** (user 2026-10-10; the usage statistics moved to `FUTURE.md` the same day):
the site has accounts, mails and uploads but only an imprint; add a privacy page (GDPR Art. 13: controller, purposes, legal
bases, retention, recipients incl. the hosting and database providers, rights)
and link it from the footer, the registration form and the mails. The cookie notice shrinks to what is true: the
site stores only what it needs (session, theme, banner state); no consent banner while nothing else is stored. The legal text needs a check by the university's data protection office.

**Credits page revision** (user 2026-10-10; narrowed 2026-10-12: in 0.6.1.0 only the DBU "sponsored by" logo and reformatted funding statements; the partners' logos and the thank-you notice wait for their consent): the ZirKuS paragraph gains the DBU funding logo (the "sponsored by"
variant, as the funder's guidelines ask; files in the gitignored `reference/zirkus_logos_refs/`, copied into
`public/` as needed) and a notice thanking all project partners for their support and valuable feedback during
development, with the partners' logos (five files there). The page itself gets the 0.6 style (theme colours instead
of `text-blue-500` links, light and dark logo handling). To settle: the partners' full names and links, and that
each partner agrees to its logo being shown.

**Ferroscan to reinforcement layout** (user 2026-10-10; 0.6.2, user the same day; **moved to the candidates of 0.6.3 by 8.150**; to grill before): the gitignored prototype
`reference/ferromodeller/` (a GH CPython component, MIT) reads a Hilti PROFIS Detection report image (two panels: the
plan / C-scan strip on top, the cross-section / B-scan below with blue / green cap markers per bar and layer,
magenta cover arrows and spacings), finds the caps and the magenta datum line, and with typed values (scan length,
covers, diameter, bar length, a placement plane) draws one straight bar per cap. Goal: make it the way CSC records
Ferroscan data from Rhino / GH. (a) A `csc_gh` module and GH components: read the report image (PNG; the PDF's
aggregate text, i.e. width, diameter, bar count and cover statistics, read too), detect the bars, place them on a
plane picked on the piece in its stored coordinates, preview, then build a `reinforcement_layout` payload with
`basis: scan` (the instrument block filled: covermeter, Hilti, the model; per bar `cover_mm`, `diameter_known`)
and upload it as a draft (8.127) through `AddEvidence`. (b) The report image (and the PDF) travel as attachments of
the record. (c) "The image in 3D": the record also stores where the image sits on the piece, i.e. the C-scan strip as
a textured rectangle on the scanned surface and optionally the B-scan as a textured vertical section along the scan
line (corners in stored coordinates plus the pixel crop of the image); the web shows the image as an attachment and
the viewer draws the textured quads with the bars as an overlay (for signed-in users, since attachment files are
theirs only, 8.13). (d) Several scans of one face ("langs" and "quer") combine into one layout or stay separate
records (RL1). (e) Depth from the image's depth axis instead of typed covers, and the detection constants tuned on
more reports, are later steps. Grill: the payload / attachment shape for the placed image (new field on the scan
basis vs. a generic "image placement" for any attachment), detection on the server vs. in GH only, PROFIS layouts
other than the sample (2047 x 1465), and GH component changes (user's OK given with this request).

**Snapshot ids in the web, for hybrid work with GH** (user 2026-10-10): the component page offers "Copy ID" and
"Copy as Grasshopper panel" for the identity only (`ComponentHeaderStrip.tsx`); a version's snapshot id (what
`FetchSnapshot`, `AddEvidence` and the reinforcement builder need) is nowhere to see or copy. Proposal, to confirm:
one shared id chip (the short id in monospace, the full id on hover, copy on click, a menu item "Copy as Grasshopper
panel") used wherever an id matters: the snapshot id of the shown version next to the version selector and in the
History rows of every version, the record id on each evidence record, and the identity id as today; Browse rows get
"Copy snapshot id" in their row menu; `?snapshot=<id>` on the component page opens that version, so an id pasted
from GH leads straight to it; the GH panel copy carries the parameter name the component expects
(`ComponentID`, `SnapshotID`).

**Provenance editing gaps** (2026-10-10, found while completing a ZirKuS beam): the web provenance dialog
(`ProvenanceEditDialog.tsx`) edits kind, date, place, works, position, connections and detachability, but not
`origin.performed_by`, `method` or `notes`; and an `Actor` has no link field, so a contractor's website can only go
into the notes. Add the three fields to the dialog (actors as in the evidence form, with the profile, 8.133) and an
optional `url` on `Actor` (organisations; shown to everyone like the organisation). Until then
`scripts/db_maintenance/copy_provenance_capture.py --contractor/--contractor-url` sets them through the API.

**Component preview drawer** (user 2026-10-10): the preview from Browse (the thumbnail in
`ComponentOverviewDataTablePreviewCell.tsx`) and from the component map (`ComponentMapPageClient.tsx`, a second copy)
opens a full-width bottom sheet with the full viewer and its menus, a centred "Preview" title and a row of 200 px
buttons: a remnant of 0.5. Keep the preview, make it compact and quiet: one shared preview panel for both pages; on
desktop a side sheet of about 420 px (the list or map stays visible), on a phone a bottom sheet of about 60 % height;
the viewer without toolbar and menus (orbit and zoom only; `ComponentViewer` already has `toolbar` and
`compactDesktop`); a slim header with name, catalogue number and dataset; one "Open" button plus small icon actions
(locate by QR, close); arrow keys or next / previous to step through the visible rows. To confirm in the grilling.

**CSC logo** (user 2026-10-10): the web shows only the lab's logo (`public/logo/ddu_logo_*.png`). Create a logo for
CSC itself: a mark and a wordmark, light and dark variants, SVG source plus PNG exports; favicon and app icons
(Next `app/icon`, `apple-icon`), the sidebar brand next to or instead of the lab's logo, the PDF passport, the mail
template, an Open Graph image, the Grasshopper interface page. Grill: who designs it (in-house, student, a designer),
the relation to the lab's logo (co-branding, "by" line), whether the GH component icons (`resources/gh_icons`) follow
the same style, and the licence of the files.

**Mail templates** (user 2026-10-10): today one inline template in `src/backend/services/email_service.py` (8.124 d:
plain text + HTML, escaped, the blue CI colour, `[CSC]` prefix, footer with `/imprint`) serves the verification,
reset, invitation and member-added mails. Give them a designed layout with the CSC logo (depends on the logo).
Grill: template files (e.g. Jinja2 under `src/backend/templates/mail/`) instead of strings in code; how the logo
travels (hosted URL on the public static host vs. inline CID attachment; many clients block remote images); dark
mode in mail clients; an admin preview and "send me a test mail" page; which further mails come with 0.6.1.0
(e.g. moderation outcome, reservation notices) so the template covers them.

**Toolchain leftovers after phase F (2026-10-12; done in a phase F addendum the same day, user):** `next` 16.3.8 --> 16.4.x as a small separate bump (build and
restart); remove the unused native `bcrypt` dependency (nothing imports it, `npm ci` builds it for nothing). The
server runs Node 22.23.2 (user 2026-10-12; Next 16 needs >= 20.9; noted in the deployment README). Since
phase F `images.unoptimized` is true everywhere and `sharp` is excluded from the standalone trace: its prebuilt
binaries need glibc >= 2.25 (0.33 / 0.34) or 2.28 (0.35), the server has 2.17, so it never loaded there; revisit only
with a server move.

**Inline geometry budget (0.6.2, decision 8.148, user 2026-10-16):** inline meshes at most 1000 faces (original above that as `detailed.ply`, the 8000-faces-inline rule removed), inline clouds at most 1000 points with the staging threshold at 1000; `csc_gh/build.py` constants and `mesh_levels`, the web snapshot form, the import tools, tests; re-run the EPFL stone prepare before its production import.

**Open-data imports, follow-ups (0.6.2, from the reviews of 8.145 / 8.146, 2026-10-15):** (a) a marker for an uploaded full point cloud on the snapshot (like `mesh_ply_resolutions` for meshes), so an import resumes without reading the Cache-Control of `GET /snapshots/{id}/point_clouds/0.ply`; (b) one `POST /snapshots/{id}/submit` answered 500 during the stone import right after the mesh uploads (stone B02, local instance, retry fine; traceback not kept): watch for it on production and reproduce (suspect: the sync derive of the upload against the submit etag). **Closed 2026-10-16 (T2):** the 500 came one second after the importing machine resumed from a 16-minute standby (system event log against the import log); no application defect; not reproduced with B02 alone, all 452 stones in sequence, or concurrent uploads and double submits. An unhandled pymongo error still ends as a bare 500: a handler answering 503 with `Retry-After` and a logged traceback goes with T3.

**HKS v2 (user 2026-10-12, research item next to O25; 0.6.2, moved to the candidates of 0.6.3 by 8.150):** the pooled HKS of `apps/descriptors/hks.py` carries
little meaning: with M-orthonormal eigenvectors the mass-weighted mean per time is the heat trace over the area,
`sum_i exp(-lambda_i t) / A`, whose leading term after area normalisation is the same for every shape; 64 eigenpairs
truncate the short times; the global L2 normalisation lets the mean half dominate the variance half. 0.6.1.0 hides
the HKS curve card (code kept behind a flag) and drops HKS from the selectable map bases (the cache may keep it). v2:
store per-point values (also for the level 2 heat map); pool the distribution of the log HKS per time (e.g. 10 / 50
/ 90 % quantiles) standardised per time across the catalogue, no global L2; consider ShapeDNA (the first k
eigenvalues over the first, already computed). Adopt only after a retrieval check (nearest neighbours of reference
pieces look sensible); new `HKS_VERSION`, recompute through the runner.

**Candidates already logged elsewhere, to sort into 0.6.1.0 or later:** O26 (user-created datasets); the IFC export
(above); HKS as a component map basis (above) and the HKS visualisation in the viewer (level 1: the HKS curve in a
descriptors panel; level 2: a per-point heat map with a time slider, needs per-point values, i.e. a new HKS version);
RL3 colour-coding and RL8 steel grade; the SH descriptor (O19--O25, licence first); the npm audit updates and the
lint refactor if 0.6.0.x does not take them.

### 0.6.1.1 --- security patch --- decided 2026-10-13 (8.144); size M

From the read-only review of main `228b84b2` (2026-10-13). No critical or high finding. One branch `v-0.6.1.1`,
one review; each item gets a test that fails before the fix. No GH component change.

- **S1 one sign-in verifier (8.144 f; review F1, I2):** `app/api/auth/[...nextauth]/route.ts` `authorize` posts the
  credentials to `/auth/token` only and maps 401 / 403 to `null`; delete the Mongo lookup and the bcrypt compare;
  remove `mongodb`, `bcryptjs`, `@types/bcryptjs`, `lib/mongodb.ts` and the frontend `MONGODB_*` variables
  (`frontend.ini.example`, README); log the outcome without the identifier. A vitest for the token exchange.
- **S2 security headers (8.144 g; F2):** `headers()` in `next.config.ts` for every path; a test that asserts the list.
- **S3 server-side backend client (F3):** one `serverBackend(path)` in `lib/` that reads the token with `getToken`
  and calls `FASTAPI_URL` with `Authorization`, the client header and the forwarded address; use it in
  `app/components/page.tsx`, `app/components/[component_id]/page.tsx`, `app/id/[uuid]/page.tsx` instead of a base
  built from the Host header.
- **S4 catalogue filter regex:** `identity_filters._exact` escapes its value (`re.escape`); `original_function`,
  `material`, `dataset` get a `max_length` like `q`.
- **S5 blocking work off the event loop:** the OBJ conversion in `get_snapshot_mesh` and the PLY parsing in the mesh
  upload run in the threadpool; the mesh route gets a rate limit like the exports; `format=obj` is refused above a
  size cap (or cached by path, mtime and size). PIL work in the photo route runs in a thread as the evidence path does.
- **S6 image decoding:** snapshot photos are sniffed by magic bytes (`evidence/files.sniff`); `Image.open(...,
  formats=['JPEG', 'PNG', 'WEBP'])`; a pixel cap (40 MP) checked before `.load()`, for photos and evidence images.
- **S7 invitations (8.144 b--e; review A1 and the resend finding):** unreviewed datasets invite only, with one answer
  and one mail; a page `/invite?code=...` (signed in with the invited address: accept; otherwise sign in or register)
  and a route that grants an open invitation to the signed-in account whose address it names; the daily cap of 50
  invitation mails per non-admin user; member e-mails only for admins and moderators of reviewed datasets; resend
  needs the current `invite` permission. Tests: no account test through either route, resend after demotion, the cap.
- **S8 logs without people (8.144 h; I1):** `usermaintenance.py` logs counts and ids only, uses `get_database_name()`
  and also matches expiries stored as ISO strings; `invitations.py` member notice failure without the address; the
  cron lines in `crontab.example` write dated daily files and one daily line deletes files older than 14 days; the
  heavy lock moves from `/tmp` to `~/csc/shared/locks/heavy.lock` (README and 8.130 note).
- **S9 error bodies:** `/health/db` answers `{'ok': False}` with 503 and logs the error; one `internal_error(exc,
  where)` helper replaces `detail=str(exc)` in 500 answers (review list of 66 sites); no file system path in a detail.
- **S10 auth details:** a dummy bcrypt check for unknown identifiers at login; `resend-verification` takes a typed
  body (EmailStr) and sends in a background task with the reset route's per-address cap; verification tokens stored
  as SHA-256 with a sparse index (open plain tokens stay valid until they expire, at most 24 h); `DuplicateKeyError`
  at registration answers 409; `JWT_SECRET` under 32 bytes refuses to start; the legacy `username` / `email` claims in
  `lookup_user_from_token` go.
- **S11 pins:** `trimesh>=5` and `skip_materials=True` in both `trimesh.load` calls; `reportlab` and the web stack
  (fastapi, starlette, uvicorn, gunicorn) pinned in `constraints.txt`.
- **S12 proxy trust:** `conf.py` sets `forwarded_allow_ips` from `CSC_TRUSTED_PROXIES` (README section updated); the
  PDF ETag includes the API base; `bind = ':8000'` stays (Uberspace web backends need it).
- **S13 anonymous dataset list (A5):** the same match as `_component_counts` (published, not withdrawn, public).
- **S14 privacy page:** the sign-in cookie lasts at most 24 hours; accounts are deleted on request; location data
  is removed from photos; "Last updated" bumped.
- **S15 CI:** actions pinned by commit SHA (Dependabot for actions); `contents: write` only on the publish job of
  `release.yml`. User, in the GitHub settings: the `production` environment requires a reviewer; tags `v*` protected.

Server notes for the deploy: the frontend `.env` loses `MONGODB_*` (harmless if left); paste the new crontab;
`mkdir -p ~/csc/shared/locks`.

### 0.6.2.0 --- robustness release --- scope decided 2026-10-16 (8.150) --- released 2026-10-18

Branch `v-0.6.2.0`. No feature work beside the hardening. Items to cut into tasks before the build:

- **A inline geometry budget (8.148):** see "Inline geometry budget" in the 0.6.1.0 backlog above.
- **B open-data import follow-ups:** see "Open-data imports, follow-ups" above (cloud marker; the submit 500).
- **C structural items deferred by 8.144 (a):** one load-and-authorise helper; one change-log writer; logging instead
  of `print`; a settings object; early body-size rejection; a shared rate-limit store and a per-account throttle;
  PyJWT; CSP with nonces; signed `SHA256SUMS`; per-file hashes for user objects; a backend read-only flag for
  maintenance; the username character set after a check of the stored names; the module splits; the test gaps.

**Tasks (cut 2026-10-16; one builds at a time, the user commits after each review):** T1 = A + B (a) (sent
2026-10-16); T2 = B (b), reproduce first; T3 settings object and logging; T4 load-and-authorise helper, change-log
writer, module splits; T5 PyJWT, shared rate-limit store, per-account throttle, early body-size rejection, username
character set; T6 CSP with nonces; T7 release attestations (8.153), per-file hashes for user objects and no self-healing in `CSC_Update` (8.155, worked out with the user; one `.ghuser` export, with the "1000 points" text of `FetchReducedGeometry`), read-only flag (8.154). T5 uses the MongoDB rate-limit store (8.152) and takes three items of a performance check (user 2026-10-17): `maxPoolSize=20` on both `AsyncMongoClient`s and the rate-limit store's client (M0 allows 500 connections); the one-off `reviewed` backfill (8.139 c) leaves the API startup (all 7 datasets carry the flag, dump 261016); the token is decoded once per request and kept in `request.state` (never a decode without verification). The test
gaps go with the task that touches each area.

**Release steps of 0.6.2.0 (the maintainer runs each one):** (1) once on the server: the `gh` CLI binary in `~/bin` and a stored token for it (deployment README, step 2b); (2) the backend environment checked against the server notes of the changelog (URLs, limits, `SMTP_DEV_MODE` off, `JWT_ALGORITHM`), the database user's rights on `rate_limit_counters`, and `NEXT_PUBLIC_STATIC_BASE_URL` set in the CI build or `NEXT_STATIC_BASE_URL` in the frontend environment; (3) a dump and an assets backup; (4) `touch ~/csc/shared/READ_ONLY`; (5) the deploy: the 0.6.1.1 deploy script runs first and repeats itself with the new one, which verifies the attestations; (6) checks in read-only mode (sign-in, the pages, `/health/db` reports `read_only: true`, the banner shows); (7) `rm ~/csc/shared/READ_ONLY`, one write checked, the crons run once without the skip line.

**Viewer opacity slider** (user 2026-10-20; 0.6.3.0 T4, after T3, 8.165 C): one slider in the web viewer's Overlay panel (0--100 %) that dials the piece itself, i.e. whatever body layer is visible (mesh, proxy, point cloud, the mesh edges), while the overlays stay as they are (reinforcement bars, evidence marks, marker points, fixtures, grid), so e.g. the bars inside a piece show through. Materials are created in the loaders and some are cached across viewers, so the opacity is applied per viewer (cloned materials, never the cached ones); below 100 % `transparent` on and `depthWrite` off; a native range input styled like the panel, no new dependency. About half a day. Added to T4 (user 2026-10-21): the "Show mesh" and "Show point cloud" checkboxes go; the detail switches (Proxy / Preview / Reduced / Original, and Preview / Original for the cloud) get an "Off" choice instead (display only, back to the previous level); "Show edges" stays and moves to "Overlays"; the slider fades whatever body layer is not Off. The two switch rows carry a visible label, "Mesh" and "Point cloud" (user 2026-10-21). Defaults (user 2026-10-21): a piece with a mesh starts with the point cloud Off (as the old hidden checkbox did); a piece without a mesh starts with the cloud shown.

**0.6.3 scope (8.165): the read-only MCP layer and the GH device sign-in; the rest moves to 0.6.4 or later.** Build order (user 2026-10-20): T1 the access tokens alone (collection, hashing, scopes, expiry, revoke, last used, auth check, token page); T2 the MCP layer with OAuth for Claude's connectors (8.168); T3 the device sign-in as the OAuth device grant (8.168 f); T2 hard requirements from the T1 review: a refresh token never passes the access-token check (own prefix, no catalog scope); `/mcp` and the OAuth token endpoint open under the read-only flag, the rotation write under the flag decided explicitly; the `WWW-Authenticate` value a parameter of the check so `/mcp` sends `Bearer resource_metadata=...`; the lookup half of the check split from its HTTP half for the SDK's verifier; the 10-token limit counts kind `pat` only; T2 tools (user 2026-10-20): `search_components` (filters like Browse, a page of short entries), `get_component`, `list_versions`, `get_version` (geometry as summary and link only), `get_evidence`, `list_datasets` / `get_dataset`, `get_timeline`, `similar_components` (from the similarity-map cache, with distance); all read-only on the existing loaders, every answer with its web link; no write tools, no full meshes, no query language or export tool at first; what MCP sees (user 2026-10-20): what the token's owner sees in the web app (an admin: private and unreviewed datasets, withdrawn versions included), with no personal data beyond what pages show (usernames, no e-mail, no account details; no tool for users or invitations), and every non-public record marked in the answer (`visibility`, `status`); sign-in lifetime (user 2026-10-20): OAuth access token 1 hour; refresh token valid 30 days after its last use and rotated on every use; a hard limit of 90 days from the consent, then Allow again; revoking a connection ends both; the consent page shows the redirect host prominently (the client name only as secondary text), "Read access to the catalog, as you see it", Allow / Deny, nothing remembered; T2 defaults (sent 2026-10-20): DCR only (no CIMD), registrations unused for 30 days deleted; per-address limits on `/register`, `/authorize`, `/token`; `/mcp` and token rotation work under the read-only flag, new consents get its 503; discovery at `/.well-known/oauth-protected-resource/mcp` and `/.well-known/oauth-authorization-server` on the API host, consent at `/oauth/consent` on the web; tested by the full flow in tests, the MCP Inspector locally, and one claude.ai connection by the user after the deploy; T3 platforms (user 2026-10-20): the device sign-in on Windows (token in DPAPI for the Windows user); on Windows and macOS the current username and password inputs stay as the fallback; T3 component (user 2026-10-20): the loopback flow of 8.168 f instead of the device grant; new button inputs `SignIn` and `SignOut`, `Refresh` removed (the token renews itself); the stored token signs in automatically on every later run; connected `Username` and `Password` win over the stored token; with neither, the status asks to press SignIn (Windows) or connect Username and Password; `SignOut` deletes the stored token and revokes it on the server; T3 sent 2026-10-20 (loopback listener off the UI thread, a fixed public GH client preferred, the GH access token preferably the normal CSC JWT of 1 hour, DPAPI storage per Windows user and server address, `CSC_CLIENT` 0.6.3.0); the password fallback keeps the 6 hours of 8.166 and, with `Refresh` gone, signs in again once by itself on a 401; T2 and T3 build on T1 only. One token collection (user 2026-10-20): `access_tokens` with `kind` (`pat` for MCP, `device` for the GH client) and scopes (`read:catalog`, `gh:client`); hashing, expiry, revoke, last used, the auth check and the list in Settings are shared; a token is valid only within its scope (a PAT only on `/mcp`, a device token only exchanged for the short-lived JWT). T3 also renews the GH client's JWT automatically from the device token when it runs out (no Refresh input), and the GH token lifetime of 8.166 (6 hours) then goes back to about an hour. PAT lifetime (user 2026-10-20): chosen at creation from 30 days, 90 days (default) or 1 year; no token without expiry; the page shows the expiry and offers "renew" near it (a new token, the old one revoked); an admin can revoke any token. Token form (user 2026-10-20): `csc_pat_` plus 32 random bytes (base64url), shown once with a copy button; the list shows the first 8 characters after the prefix, name, scope, created, last used, expiry; stored as SHA-256 only (no bcrypt: random tokens cannot be guessed and every MCP call stays fast); at most 10 active tokens per user; every request checks the database (no cache), so expiry and revoke act at once. Who holds which token (user 2026-10-20): PATs only for admins, the role checked again on every request (a lost admin role stops the tokens at once), opened to more roles later by one setting `CSC_PAT_ROLES` (default `admin`); device tokens (T3) for every signed-in, verified user, giving only that user's normal GH access; everyone sees their own tokens, admins also a list of all tokens with revoke. Candidates of 0.6.3 (moved out by 8.150): Ferroscan to reinforcement layout; the IFC export with the PROV-O /
JSON-LD / GraphML form of the timeline (8.140 h); HKS v2 and HKS level 2; RL8; the GH device sign-in (`FUTURE.md`); a read-only MCP layer (user 2026-10-20): an MCP endpoint in the backend (`/mcp`, stateless HTTP) whose tools reuse the record loaders and serialisers of the REST API (search, component, versions, evidence, datasets, timeline, similar components; geometry as summary and link), reached with personal access tokens (stored hashed, scoped `read:catalog`, expiry, revoke, last used; admins only at first), a token page in the admin settings, and `/mcp` exempt from the read-only flag; the tokens are the same foundation the GH device sign-in needs.
The SH descriptor stays blocked on its licence.

---

### Roadmap after 0.6.3.0 --- proposed 2026-10-21, adjusted by the user the same day; each release is grilled before it is built

**0.6.3.1 --- hardening after the release (about 3 days):** a per-address limit on failed access-token lookups;
token clean-up (tokens of deleted accounts removed, revoked rows deleted after about 90 days); viewer: a version
switch with the mesh Off no longer loads the hidden level; viewer: mesh edges and faces clip each other at some
angles (user 2026-10-21) --- the edges should win, most likely through `polygonOffset` on the mesh material so the
faces sit a hair behind their edges (edges drawn with depth test off would show the hidden back edges too, so not
that), and check the camera near / far planes against the piece's size in case the faces themselves are cut
when zooming in; stale file markers after a geometry PATCH on a draft (`mesh_ply_resolutions`,
`point_cloud_files`, `FUTURE.md`); the geometry cache drops the descriptor keys on a frame-only cut; the planar
outline's vertex limit counts holes; the paired rebound linked on the core record's evidence card; RL1 checked
(two layouts on one piece show both cards and bar sets); the snapshot-scoped fold confirmed by a test;
housekeeping (em dashes as empty values in `app/admin/users/page.tsx` and `InvitationsTable.tsx`, the long
README line on `SMTP_REPLY_TO`, `tests/api/test_mail_templates.py` and its `delenv`, a fresh `npm audit`). Added (user 2026-10-21): `invoke release-prep` (the CHANGELOG date, `.zenodo.json`, `check_version --tag`, `tests/ci` in one step) and `bump-version --gh` leaving `DDU_CSC_Session.py` alone when its client version already matches. And `.claude/launch.json` committable: a launcher that finds the `csc` environment without an account path, `serve_migrated.py --dump latest` (empty exports load as no documents), one `backend-local` / `frontend-local` pair.

**0.6.4 --- search and the location map (about 7--9 days; user 2026-10-21):** a catalog of about 2300 pieces
needs new kinds of questions more than indexes. (a) **Dimensions** ("what fits?"): range filters on the stored
size (`bbx`) per axis with tolerances, an orientation-independent envelope match (the three sizes sorted), and
sorting by closeness to the asked size; in MCP as parameters of `search_components` or a `find_fitting` tool
(about 1--2 days). (b) **Location**: the versions' `location` and the origin building's `Place.location` also
stored as GeoJSON points with a `2dsphere` index (Atlas M0 has it); `$geoNear` gives the nearest k or everything
within a radius, with the distance in metres, combined with the other filters; in MCP as `near` (coordinates,
radius, count) or a `find_near` tool (about 1--1.5 days on top of (c)). (c) The **location map** (user
2026-10-21): a second map page next to the Similarity Map with every visible component as a marker (clustered),
a click opening the shared preview panel, visibility as on Browse, on the field and index of (b); to grill:
which location (current, origin, or both as layers), the map library and tile source (the CSP of 8.164 allows
only the Google embed; OpenStreetMap tiles send each visitor's address to OSM and allow light use only, so the
CSP and the privacy page change) (about 2--3 days). (d) **Sorting and overview**: sort by catalog number, date,
size, distance, dimension match, rising or falling; a `catalog_overview` MCP tool with counts by material,
function, dataset and shape class (about 1 day). (e) **True similarity**: kNN on the descriptor vectors
(radial signature, scalars) instead of the 2D map layout, a NumPy pass at this size (no Atlas Vector Search
needed), combinable with (a) and (b) (about 1--2 days). Later: search by measured properties from the evidence
fold (once it is clear which quantities are searched); Atlas Search for typo-tolerant text (weakest gain).

**0.6.4 decided (grilling from 2026-10-21):** (a) dimensions (8.169): two modes on the sorted sides of the current `bbx`, *about this size* (within a tolerance, closest first by the largest relative deviation) and *can hold this size* (every side at least the asked one, least waste first); the per-axis filters and `bbx` sorts stay. Tolerance: one per query, mm or %, default 10 %. Web: a "Fits" section in Browse's "More filters" (size in any order, mode, tolerance), the list sorted by the match with deviation or waste per row, state in the URL. MCP: `fit_mode`, `size_mm`, `tolerance` on `search_components`, no `find_fitting` tool. (b) and (c) location (8.170): the current and the origin location both as GeoJSON points with a `2dsphere` index each; near search names which one; the map has both as layers, Current by default; filling in origin coordinates is a separate data task. Web: latitude and longitude of the origin place editable in the origin form (a pasted "lat, lon" accepted). Map (8.171): Leaflet and `leaflet.markercluster` bundled from npm, tiles from `tile.openstreetmap.de` (FOSSGIS e.V.), CSP `img-src` plus that host, one paragraph on the privacy page. Near: `near_lat`, `near_lon`, `near_layer`, `radius_km` on `search_components` (no `find_near`), a "Near" section in Browse (point, layer, radius; "Near this piece" from a component page), sorted by distance. Registration (8.172, added by the user): an empty `CSC_OPEN_REGISTRATION_DOMAINS` (the new default) means invite only, with an invite-only register page; with domains set the register page says it is open to certain domains and lists them in a tooltip; no TU Darmstadt texts or placeholders. Map page: Browse's filter bar (URL state, "Show as list"), layer switch, clusters with counts, colour-by and legend of the Similarity Map, marker click opens the preview panel, empty-spot click offers "Search near here". (d) Sorting (8.173): keys `volume`, `distance`, `match`; Fits sorts by match, Near by distance, both: distance; a sort menu in the card view; `sort` and `order` on `search_components`. Overview: MCP `catalog_overview` (stats with the search filters: total, counts by material, function, dataset, shape class, circulation, side ranges, location coverage, non-public count). (e) Similarity (8.174): kNN on the standardised descriptors (basis `radial_signature` by default), `similar_components` with `basis` and the search filters, a "Similar pieces" card behind a retrieval check. Build order (user 2026-10-22): the registration task (8.172) first as hardening, then dimensions and sorting, location, the location map, overview and similarity; the kNN search also in Grasshopper. T6 (GH, after T4): `FetchSimilarComponents` (IdentityID, Basis, Count, filters; ComponentPassport, Distance) and Fit and Near in `FetchFilteredComponents`. Waste share (8.169, user 2026-10-22): at most 99 % unless exactly 100 %. Vertex colours from the texture (8.175, added by the user 2026-10-22): the Create components compute vertex colours from the texture of the referenced Rhino object's render material when they stage a mesh; no extra input. The texture wins over existing vertex colours, with a remark. Bilinear sampling at each vertex's texture coordinate, each level from its own coordinates. Built inside T6 (one Rhino 8 export, one `bump-version --gh`). Coordinate boxes (8.170 amended, user 2026-10-22): one shared latitude and longitude pair in every location form, a pasted pair fills both, a comma jumps to longitude, no separate paste field. Similar pieces card (8.174 amended): "Show more" up to 24 in the card with "Show fewer"; series siblings stay separate tiles. Privacy and imprint (8.176, user 2026-10-23): the maintainer is the controller, TU Darmstadt is not; the Google map hover preview in Browse goes (the link stays), the CSP drops frame-src; cookies row corrected; imprint on the DDG.

**0.6.4.1 --- hardening (user 2026-10-27, before 0.6.5):** first the MCP connector, from two chat reports. (a) Search by evidence method (8.177): `evidence_method` on the catalog list, `has_evidence` on the MCP search tools; Browse later. (b) Recognizable connector: instructions that name the domain in English and German (reused and salvaged building components, Bauteile, Wiederverwendung, concrete walls and beams, reinforcement / Bewehrung) and say to use these tools before a web search for such pieces; `website_url` and `icons` on the server; a title and `readOnlyHint` on every tool; tool descriptions that name the evidence methods. (c) The geometry summary drops the `reinforcements` count (always 0 since step 6d moved the bars to evidence, 7.8) and gains the reinforcement layouts of the version (records and bars) with a pointer to `get_evidence`. (d) The evidence list rows of a `reinforcement_layout` carry the bar count, basis, specs, diameters and cover; `performed_by` shows an organization instead of `null`. (e) The write model no longer accepts `geometry.reinforcements` (7.8). (b) to (e) confirmed by the user 2026-10-27; the server icon is the web app's `favicon.ico` until there is a CSC logo. (f) The "Similar pieces" card (8.174 amended): in the left rail on a wide screen, smaller tiles. (g) The `bbx` facet of `/identities/stats` buckets the largest side with edges from the metre era (0 to 1000, then ">=1000"), so in millimetres nearly every piece lands in the last bucket: edges in millimetres instead (for example 100, 250, 500, 1000, 2000, 5000, 10000), checked against the analytics page. (h) The Similar pieces card offers "Show more" only when the first answer says there are more than 6 neighbours, not when there are exactly 6. (g) and (h) added by the user 2026-10-27. (i) Frontend advisories: `undici` (high, fixed in 7.30.1) and `fast-uri` (two medium, two low, fixed in 3.1.9) come only through `shadcn`, the component generator, which is a `devDependency` already; the lockfile takes the fixed versions. (j) The import scripts (`scripts/import/requirements-import.txt`) move to Pillow 13.0.0 (20 alerts); they run locally, the accepted risk of the backend pin stays as it is. (k) E-mail verification drops the fallback to a token stored in plain text (the TODO for 0.6.2 in `auth.py`; such tokens expired 24 hours after 0.6.1.1). (i) to (k) added by the user 2026-10-27. (e) stays with `geometry.reinforcements` only (user 2026-10-27): `geometry.marker_points` is still written by the robot rubble scan pipeline, which is not in use now; both go to the backlog below. (l) Seven tests in `tests/grasshopper` hard-code the client `gh-userobjects/0.6.3.0` and fail since the version bump of 0.6.4.0 (CI does not run `tests/grasshopper`): they read the expected client from the `CSC_CLIENT` line of `DDU_CSC_Session.py` and check that it is not newer than `VERSION` (the rule of `check_version.py`), so a bump with or without `--gh` no longer breaks them; found during T1, built with T3 and a fix round after the bump. (m) "Show in viewer" on the card of a reinforcement layout (8.178, user 2026-10-27): the viewer draws that one record on its version whatever its status, so a submitted draft can be seen and checked; built as T4.

**0.6.4.2 --- second hardening, web and backend (user 2026-10-28, before 0.6.5; 8.179):** no Grasshopper changes (`bump-version` without `--gh`). (a) #35: on session expiry a component page that is not public to anonymous visitors (and a draft view on a public one) is no longer exempt from `SessionMonitor`; a public piece stays readable. (b) #37: a `reinforcement_layout` event in the History graph opens the layout in the viewer as "Show in viewer" does (8.178); other records scroll to their card, also a corrected one. (c) #39: credits and imprint take the box width, padding, text sizes and link style of the privacy page; wording, structure and the card title icons stay. (d) #34: `organization_url` in the profile, copied into the "You" performer, and "Add my organisation" in the performers field. (e) The Browse filter for the evidence method (8.177; the list already takes `evidence_method`). (f) 8.178 follow-ups: the diameter colour mode with a chosen layout; the legend key by layout id. (g) `shadcn` (dev only) to >=4.22.1, about two weeks old from 2026-11-01; the maintainer runs the update. (h) The 61 warnings of `invoke test-release`: sorted, the cheap ones fixed, the rest reported. (i) The unused `bbxX` type removed from `lib/analytics.ts` (whether the backend keeps the field depends on other readers, to be reported).

**0.6.4.3 --- Grasshopper hardening (user 2026-10-28, after 0.6.4.2; 8.180):** only the Grasshopper side (`bump-version --gh` first, then the export in Rhino 8). (a) #40, with #32 and #33 as its first cases: the scan of 2026-10-28 found eleven components that report a missing input with `_addError` through `BuildError` (`Actor`, `ApplyFrame`, `Capture`, `ComputeFrame`, `CreateComponentIdentity`, `CreateComponentSnapshot`, `FetchReinforcementLayout`, `IdentityMetadata`, `Origin`, `ReinforcementLayout`, `SnapshotMetadata`; `AddEvidence` already warns), fourteen outputs started as `''` or `None`, and an `empty_outputs()` that returns `None` in 47 components. The fix belongs in the shared library (a missing-input error reported as a warning, an empty tree helper) and then in every component; the implementer lists each component and what changed. (b) #36: `ReadFromD2P` resolves the D2P component from a tagged member object, with a live check in Rhino by the maintainer. (c) The descriptions of `ApplyFrame`, moved from 0.6.5 (e). (d) The 8 `PytestUnhandledThreadExceptionWarning` of the Grasshopper tests: cause found, fixed or explained.

**0.6.5 --- reinforcement from Grasshopper (about 6--8 days; moved from 0.6.4 by the user 2026-10-21):** (a) units
in GH: every component scales by the document unit (a prerequisite for placing scans); (b) RL8, a GH builder
for the `rebar_spec` claim and its display, grilled together with (c); (c) Ferroscan to reinforcement layout,
parts (a) report reader, detection, placement and a draft through `AddEvidence`, (b) the report image and PDF
as attachments, (d) several scans of one face; (c) "the image in 3D" later. (e) `ApplyFrame` stays as it
is (user 2026-10-27): its `Frame` output is the frame used, in the stored coordinates (where the piece
sat before the move), not the frame of the moved piece. The descriptions of the component and of the
output say so plainly and point to `DisassembleComponent`, whose `Frame` applies `csc_placement` and so
gives the frame where the moved piece sits; moved to 0.6.4.3 (8.180).

**0.6.6 --- interoperability (about 5--7 days):** the IFC export (`compose?format=ifc`; first the `ifcopenshell`
wheel check for the server, then IFC4 vs IFC4x3 and single piece vs selection); the timeline as PROV-O /
JSON-LD / GraphML (8.140 h); optionally a vocab page the JSON-LD `@vocab` resolves to.

**0.6.7 --- shape descriptors (research, about 3--7 days):** HKS v2 behind a retrieval check (nothing ships if
the neighbours do not look right); if it holds, the HKS basis on the Similarity Map, the level 1 curve and the
level 2 heat map, and the descriptor kNN of 0.6.4 (e) gains from it; the SH descriptor only if its licence has
arrived.

**Later, not yet scheduled --- modular Grasshopper components (user 2026-10-23):** the large Grasshopper
components, `FetchFilteredComponents` first (about twenty inputs since 0.6.4), become small components that are
combined: for example one component per filter group (material and function, dimensions, fit, near, circulation)
that each output a filter object, and one fetch component that takes any number of them, in the way the builder
objects of the Create components already work. To be grilled before it is planned: the split, how filters
combine, and how existing definitions keep working (old components kept, marked as superseded). With it (user 2026-10-23): a check that a component on
a canvas has the inputs its source declares. The access and the type hint of an input already follow the
annotation in the source's `RunScript` signature (`FitSize: list[object]` is list access without a type hint), but
`CSC_Update` leaves the inputs of a component already on a canvas as they were, so new inputs are missing there.

**Later, not yet scheduled --- the robot rubble scan pipeline (user 2026-10-27):** `src/py_modules/csc_robot_rubble_scan_processing` still builds the 0.5 shape (`type`, `assembly`, `processes`, `iframe`) and puts the scan markers into `geometry.marker_points`, which `upload_robot_scan.py` posts unchanged to `POST /identities`. Before it runs again: the 0.6 create request, the markers as `capture.markers` with role `rig` (7.7), a trial upload against the local stack; then the write model rejects `geometry.marker_points`, as it rejects `geometry.reinforcements` since 0.6.4.1.

**Later, not yet scheduled --- German as a second language of the web app (user 2026-10-28):** a language
switch in the header, the choice in a cookie (default from `Accept-Language`), no `/de/...` URLs; `next-intl`
with `messages/en.json` and `messages/de.json` and a test that fails on a key missing in either. About 6--10
days for the whole UI (about 1200--1800 strings in some 184 files), or about 3--4 days with the public pages
first. The vocabulary labels gain a German label in the vocabulary source and `generated/Vocab`; dates and
numbers follow the language. To be grilled before it is planned: the German terms (evidence, snapshot, piece,
passport) in `CONTEXT.md` first; whether the backend errors become codes, the mails get a language per user,
and the privacy page a German text (the maintainer's own); a rule for the implementer that every new string is
written in both languages. Grasshopper and MCP texts stay English.

**Outside a release (the maintainer):** the Atlas traffic measurement of 0.6.1.0 (c); the backend CI job back to `ubuntu-latest` once MongoDB
8.0 starts on the runner's kernel (SERVER-121912); `shadcn` (dev only) lifted to >=4.22.1 once that
version is about two weeks old, which clears the six remaining dev findings of `npm audit` (found in the
review of 0.6.4.1).

**Later or ideas:** the GH sign-in on macOS (Keychain); Ferroscan "the image in 3D"; MCP opened to members
(after 0.6.3.1); the CSC logo and brand, then the logo in mails, Open Graph and the favicon; the partners on
the credits page (their consent); usage statistics without cookies; timber evidence methods; the analytics
page; transactions for record plus change log; xeokit (for later, see `FUTURE.md`); a similarity-search
endpoint and the other `FUTURE.md` ideas.

## 4. Dependencies at a glance

```
P0 --(independent, first)
P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P7 -> P8 -> P9 -> P10 -> P11 -> P12 (cutover)
            (P4 needs P3's permissions; P5 needs P4's original_function for the column rule;
             P6's reinforcement layout needs P5's capture/stored-coordinate handling;
             P11 comes after P9 and P10 so it revises their screens too; 8.103)
```

## 5. Decided with the user (2026-09-28)

- **Q1** Test database: local **MongoDB Community Server** + own fixture (`pymongo-inmemory` and an
  Atlas test database rejected).
- **Q2** Vertical phases, each with its UI.
- **Q3** Review stop per phase. **The user makes every git commit** (code and documents);
  Claude leaves changes in the working tree and may suggest a commit grouping.
- **Release naming:** the pre-work release is **0.5.1.0** on `v-0.5.1.0` (formerly "0.5.0.1");
  the full evidence system is 0.6.0.0 on `v-0.6.0.0`.
- **Server work** on Uberspace is done by the user from terse step-by-step instructions.

---

## Appendix A --- Full walkthrough (acceptance of P7, rerun before cutover)

Run on `invoke dev-migrated` (dump 261001) with the frontend, once at phone width (375 px) and
once at desktop width. Accounts: `dev-admin` plus one account each for contributor, reviewer and
moderator of one dataset (four eyes needs two people). Tick every line; a failure is a finding
for the review session.

**Access and navigation (P3, 8.29, 8.86)**
1. Anonymous: a public component shows the public tier; a non-public one says "not public" with a
   sign-in link; no Recent list; nothing recorded in Recent.
2. Sign in as contributor: sidebar shows the contributor's groups only; Recent fills while
   browsing; sign out --> Recent gone and hidden; session expiry --> the same.
3. A withdrawn component: members see the record with the banner, others the tombstone; a
   duplicate redirects to its canonical piece.

**Scan and create (P7, 7.5, 8.87)**
4. Scan (or paste) a tag that is not in the catalog --> *New component* --> details, size, photos,
   optional inspection --> submit; as contributor it is pending, as moderator published and
   current.
5. Scan an unused tag --> *Cut from pieces* --> scan the parent tag --> size --> submit; after
   publish the parent shows "Split", the child its inherited fields with markers.
6. On a component page: *Cut a piece from it* opens the same form in cut mode.
7. *Record new state* (changed shape) --> new version, `effective_from` today unless set.
8. *Correct* a published snapshot --> prefilled; with a new size the dialog lists the positioned
   evidence and links each to its correction; without a new size no warning.
9. Edit page: name, notes, location, colour of the current snapshot.

**Moderation (P3)**
10. Moderation queue: publish, reject with a reason, resubmit by the author; withdraw and
    reinstate a snapshot; make another version current.

**Provenance and circulation (P4)**
11. Edit provenance (DIN SPEC / DGNB fields); on a child untick and re-tick "From the parents".
12. Take out of circulation (installed), undo, re-enter with a new origin --> earlier cycle shown.
13. Change history lists the edits with sub-fields; `/admin/materials`: add, edit, retire, delete
    an unused one, merge.

**Geometry (P5, 8.52, 8.53, 8.60, 8.85)**
14. A ZIRKUS beam lies, a ZIRKUS column stands, a rubble piece is not upside down (canonical vs
    as stored).
15. Proxy detail for a box, a prism, a cylinder and a hull; the solid, outline and distance
    overlay coincide in both orientations; "?" popovers open by tap and by hover.
16. A snapshot with a failed stage shows the notice; `/admin/geometry` lists it; Retry runs.

**Evidence (P6)**
17. Three rebound areas in one submission, one with a grid on a picked face; server median and
    discard rule shown before submit; repeat-from-my-last-record prefills the instrument.
18. A core paired to a rebound record; an attachment; a file over 25 MB refused.
19. A visual inspection with photos per observation; the condition badge updates after publish.
20. Publish as moderator, review as a second person (four eyes); the properties card shows the
    folded range, n and confidence; the timeline shows cycles, snapshots and evidence.
21. GDPR removal of an attachment: the name is blank on the record and in the change history.

**In place, batches, documents (P9, 8.104--8.106)**
22. An in-place piece shows the badge and appears under `in_place`; reserve it; *Record deinstallation* keeps the
    reservation and adds "Deinstalled" to the timeline; *Undo deinstallation* works until a later record exists.
23. On a batch: *Draw pieces* with quantity 2 --> the batch line counts them; drawing more than remain is refused;
    drawing the rest takes the batch out of circulation as "Split"; the child shows "Documents from the batch".
24. Record a document without a value, with a link: the card shows "Document" and the host as an external link; the
    properties card is unchanged.

