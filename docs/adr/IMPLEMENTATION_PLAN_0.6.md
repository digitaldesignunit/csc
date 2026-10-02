# Implementation plan --- CSC 0.5.1.0 and 0.6.0.0

**Status:** draft 3, 2026-09-30 --- accepted by the user with the changes in section 5; P0--P3 done (2026-10-02). Implements `docs/adr/DATA_MODEL_SPEC.md` (draft 5) and the
decisions in `docs/adr/DESIGN_DECISIONS.md` (1.1--8.30). Terms follow `CONTEXT.md`.
**Branches:** P0 on `v-0.5.1.0`; P1--P9 on `v-0.6.0.0`, each phase on its own `v-0.6.0.0-P<n>` branch (P2b, P3, P4, ...).
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

### P4 --- Provenance, lineage, materials --- size M
- `change_log` first (8.36, spec section 3.8, I30): one write helper used by every route that
  changes a record, retrofitted onto the P3 PATCH / lifecycle routes; `?as_of=`, `/changes`.
- Split / merge exit derived from published children (8.8): set on the child's first publish (needs
  `moderator` of child and parent datasets), `at` = earliest child `effective_from`, cleared when the last
  published child is withdrawn; tests for draft / rejected / withdrawn children and cross-dataset cuts.
- `origin` / `exit` / `past_cycles` routes (section 3.1.1, section 3.1.3, section 7.1): exit, undo, re-entry
  (server-set split / merge: first bullet); after re-entry the next snapshot defaults to the new
  `origin.at` (8.19).
- Lineage inheritance (section 3.1.2): copy-on-create, recursive propagation on parent PATCH, detach on
  child PATCH, re-inherit, merge unanimity (I17).
- `materials` collection + routes (section 2.10, section 7.7); `material_class` derivation + override (I25); delete / merge / retire (8.35).
- DIN SPEC 91484 / DGNB fields (8.38): origin `position_in_work`, `connection_types`,
  `detachability`, `construction_method`; identity `manufacturer`, `connection_features`,
  `material_separability`; section 2.11 vocabularies.
- Web: origin / exit forms and cards, lineage view with inherited markers, circulation filter,
  materials in `/admin`, "cut from..." entry point of the snapshot form (7.5).

**Done when:** propagation tests over a 3-generation lineage incl. a merge; I16--I18, I25 checked by
`check_invariants` on the rehearsal DB.

### P5 --- Geometry runner --- size XL
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

**Done when:** every rehearsed snapshot has frame, bbx, shape class, proxies, descriptors,
complexity; the user has signed off the tuning tables and the frame report.

### P6 --- Evidence --- size XL
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
- Web: evidence form from the component page (7.1: fan-out, repeat-from-last, apply-to-several),
  "?" popovers from the backend descriptions, per-observation inspection photos (7.4), position
  picking on the viewer, evidence moderation + reviewer queue, properties card (range + n),
  condition badge (7.9), timeline.

**Done when:** fold unit tests cover tier precedence, derived results, verification, inheritance
and merges; the phone walkthrough "scan --> add 3 rebound areas --> submit --> moderate --> verify" works.

### P7 --- Web completion --- size M
- Snapshot form's remaining entry points (new component, record new state, correct --- 7.5; the
  correct dialog warns about evidence positioned on the previous version, 8.16),
  wizard's optional inspection step (7.9), edit form reduced to mutable metadata.
- Every remaining 0.5 consumer of removed fields gone (`type`, `extrusions`, `condition`,
  `consumed*`, `validated`, `iframe`, `pca_frame`); client header `web/0.6.0.0`.
- Full walkthrough checklist (appendix of this plan, written during P3--P6).

### P8 --- GH bridge --- size L
- Header `gh-userobjects/0.6.0.0`; builders `Actor`, `Origin`, `IdentityMetadata`,
  `SnapshotMetadata` (7.6); `CreateComponentIdentity` / `CreateComponentSnapshot` with ~8 inputs,
  create-as-draft + submit, no PCA / reduction; robot-scan import writes `capture`;
  `ReinforcementLayout` + generic `AddEvidence` (7.8); `ApplyPCAFrame` --> `ApplyFrame`; inputs
  removed (`Type`, `Salvage*`, `Condition`, `Complexity`, `Assembly`, `Virtual`, `MarkerPoints`,
  `Reinforcements`); tooltips (dataset names) updated.
- **Done when:** the DDU aggregation and robot-scan definitions run end-to-end against a staging
  backend.

### P9 --- Cutover --- size M
1. Freeze writes on production (0.5.1.0); take the cutover dump + assets backup.
2. `invoke rehearse` on that dump --> clean report (the abort guards catch drift since 260916).
3. Deploy 0.6 backend + frontend; run section 8.1 on production in run order; `check_invariants`;
   rebuild the component-map cache (`main_component_map.py`: the cache ids changed with the 0.6
   filters).
4. Set `CSC_MIN_CLIENT_VERSIONS` to 0.6.0.0; publish the bridge UserObjects via `CSC_Update`.
5. Designs archived by step 13 (count verified).
6. After cutover: personal accounts created --> fill in the untracked `.dev/reattribute_06.json` --> step 11b
   re-attributes every `ddu` / `admin` record by the 8.24 mapping and adds the two moderators of
   every dataset (8.25); `ddu` and `admin` stay as the user- and admin-role test accounts with no
   records (8.22, 8.25); further memberships assigned in `/admin`.

---

## 4. Dependencies at a glance

```
P0 --(independent, first)
P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P7 -> P8 -> P9
            (P4 needs P3's permissions; P5 needs P4's original_function for the column rule;
             P6's reinforcement layout needs P5's capture/stored-coordinate handling)
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
