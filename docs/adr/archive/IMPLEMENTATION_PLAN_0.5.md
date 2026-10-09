> **Archived 2026-10-02.** The 0.5.x implementation plan, kept as written (ASCII-normalised).
> Superseded by `docs/adr/IMPLEMENTATION_PLAN_0.6.md`; its 0.5.0.2 moderator section by decision
> 6.5 (dataset roles). Items still open here are carried into `docs/adr/FUTURE.md`.

## Implementation Plan V 0.5+

### 0.5.0.0 - Things that need doing before 0.5 release and switch to main branch

#### 1. DONE: Reinforcement Bar Implementation

- implement reinforcement bar as inline geometry
- object consists of a polyline (list of points), a diameter and a string denoting the reinforcement steel spec
- I propose {spec, diam, [points]} or similar as signature
- objects can hold multiple of these reinforcement-steel polylines, if only one it is a list/array with one entry

#### 2. DONE: API Polish

- **DONE: ghinterface router**
  - Consolidated `downloads` and `ghupdates` routers into `ghinterface` router
  - Updated frontend and `DDU_CSC_Update` to new paths (`/ghinterface/...`)
- **DONE: User administration in frontend**
  - we need admin UI/UX for user management, set roles, set moderated datasets for moderator users, etc.
- **DONE: Public endpoints per component for DMS presentation and public demos**
  - `is_public` on component identities (default false; migration script provided)
  - Anonymous read of passport, meshes, preview, and photos for **all snapshots** when `is_public`
  - Admin toggle on component edit page; public demo banner on detail page
- **DONE: Wire orientation.py (PCA frame computation) to Add Component Wizard**
  - `POST /utility/compute-snapshot-orientation` uses `orientation.py`
  - Wizard calls it on submit to set `bbx`, `bbx_origin`, and `pca_frame` from box geometry

#### 3. DONE: Low Priority polish

- **DONE: README / gh-interface** doc refresh - gh-interface cards for `ListIdentitySnapshots`, `FetchAllSnapshots`, `FetchSnapshot` added; verify screenshots after `CSC_Update` release.
  - Cards previously carried the pre-rename names `FetchComposeAllSnapshots` / `FetchComposeSnapshot` and the output pin `ComposeJSON`; corrected to match the shipped components (`ComposeData`).

#### 4. DONE: GH Point Cloud Staging Upload

- **DONE: GH point-cloud staging upload** - `CreateComponentIdentity` manifest + `AddComponentIdentity` handoff for `point_clouds/{index}.ply` (API ready; workshop wiring still mesh-only).
- **DONE:** Point clouds supported in frontend viewers

#### 5. Preview re-generation / Expiry

- **DONE:** On new validated snapshot, preview has to be flagged to regenerate
- **DONE:** Preview generation renders point-cloud-only snapshots; meshes and extrusions still take priority when a snapshot carries both

#### 6. DONE: Descriptors for Every Geometry and Component Type

Goal was to compute descriptors for all catalog components, not just the mesh/extrusion panels the pipeline started with.

- **DONE: Point clouds in the descriptor pipeline**
  - Geometry priority is now `detailed.ply` > `reduced.ply` > inline mesh > extrusion > point-cloud PLY > inline cloud preview
  - `boxscore` / `spherescore` / `linescore` / `planescore` run on cloud-only snapshots via the cloud's convex hull, which is what those four scores read anyway, so results stay comparable to mesh-derived ones
  - Degenerate clouds (coplanar / collinear) are rejected with a clear reason rather than producing a zero-volume hull
- **DONE: Radial signature for every component type**
  - Was panel + extrusion-profile only; now applies to all types from an extrusion, a mesh, or a point cloud
  - Outline extraction lives in `apps/descriptors/outline.py`; `radial_signature.py` stays pure 2D math
  - Geometry priority is **mesh > point cloud > extrusion profile**, always the highest resolution available:
    - mesh: `detailed.ply` > `reduced.ply` > inline `geometry.meshes[0]`
    - point cloud: `point_clouds/<snapshot_id>/0.ply` > inline preview
    - extrusion profile is last; panels use the authored profile, every other type is cut from the swept mesh
  - **Panels**: full silhouette, rotated into canonical rest position; an authored extrusion profile is used only when no mesh or cloud is present
  - **All other types**: cut by the PCA centre plane, no rest alignment, no flattening, no slab widening. A beam's authored profile is its 100x200 cross-section while its PCA plane holds the 2000x200 lengthwise cut, so reading the profile would describe a different plane than a mesh or cloud of the same beam
  - New backend dependency: `shapely>=2.0` (`concave_hull`), previously only transitive via trimesh
- **DONE: Descriptor CLI recompute/reset**
  - `python main_descriptors_simple.py --recompute` walks every snapshot in `_id` order, one at a time, and overwrites every applicable descriptor
  - Combine with `--limit N` and `--dry-run` to try a subset first; cron mode (`--all` / default) still only fills missing keys

**Open decisions / follow-ups:**

- **OPEN:** `slab` is arguably as planar as `panel` and is currently treated as a solid. One-line addition to `REST_ALIGNED_COMPONENT_TYPES` if it should be rest-aligned; same question for `profile`.
- **OPEN:** `rest_position` does not pick a stable canonical rotation for symmetric outlines. A mesh and a point cloud of the same L-panel landed a quarter turn apart, reliably and identically across seeds. Once aligned they agree to 1.6% of panel scale (worst case 10%, at the rounded concave corner). **Matching must therefore compare across circular shifts, or the descriptor needs a rotation-invariant form.** Left alone for now because changing it would invalidate every stored signature.
- **OPEN:** The radial spec carries no applicability filter, matching the four scores. A component with no usable geometry is therefore re-picked by the descriptor cron every run and logs why it was skipped, rather than being filtered out at query time. Pre-existing behaviour for the scores; worth revisiting if the catalog accumulates geometry-less components.
- **OPEN (docs):** the `CSC_RadialSignature` gh-interface card describes rest position as unconditional. The component already exposes `RestPositionAlign`, so it can reproduce both behaviours, but the card should say that reproducing a non-panel descriptor needs `RestPositionAlign=False` plus the PCA-plane section curve.

#### 7. GH Add Geometry to Snapshot

- **OPEN:** ability to add geometry to an existing snapshot in Grasshopper

---

### 0.5.0.1 - Virtual Snapshot Propose/Create

- **Virtual snapshots** - users must be able to **create or propose** a **virtual** snapshot **for a given identity** (basis = current snapshot, explicit parent snapshot, or equivalent stated in the request - product rules + validation in implementation).

### 0.5.0.2 - Moderator Role Extension

- we need moderator as a role
- a moderator has admin privileges for components that belong to specific datasets
- **Q1.** Should `role` become a single enum: `"user" | "moderator" | "admin"` (one role per user, not combinable)?
- **Q2.** Field name for scoped datasets on the user document - is `moderated_datasets: string[]` OK?
- **Q3.** Defaults for existing users in the migration:
  - keep current `role` unchanged
  - add `moderated_datasets: []` to everyone who lacks it
  Is that correct?
- **Q4.** Should `admin` users ignore `moderated_datasets` (global admin stays global), or can admins also be dataset-scoped in some cases?
- **Q5.** For the pending-validation queue: should moderators see **only** pending snapshots whose identity's `dataset` is in their list?
- **Q6.** Should these stay **admin-only** (not moderator)?
  - Backend log pages (`/fastapi_log`, previewgen, descriptors logs)
  - Anything else you consider "system admin" vs "catalog admin"?
- **Q7.** Match style: exact string match on `identity.dataset`, or normalized (trim + case-insensitive)?
- **Q8.** If an identity has a missing/empty `dataset` (legacy data): moderators cannot act on it, or only global admins can?
- **Q9.** When a moderator edits identity metadata, can they **change** `dataset` (e.g. move a component out of their scope)? I'd assume **no** unless you want otherwise.
- **Q10.** Can moderators create new identities/snapshots **into** a dataset they moderate (same as any logged-in user today), or is that unchanged?
- **Q11.** Is it enough to:
  - enforce permissions on the **backend**
  - expose `moderated_datasets` in session (or a small "who am I" API)
  - update frontend admin **component** actions to show for `admin` **or** moderator-with-matching-dataset
  ...while **deferring** the `/admin` user-management screens?
- **Q12.** Should moderators get access to `/admin/validation` (filtered to their datasets), or only see actions on individual component detail pages?
- **Q13.** Session staleness: today role is fixed until re-login. OK to keep that for v1, or should we refresh role/datasets from DB on each session callback?
- **Q14.** Script location/pattern: `scripts/db_maintenance/migrate_add_moderator_role.py` with `--dry-run`, like `migrate_add_dataset_field.py`?
- **Q15.** migration script scope:
  - add `moderated_datasets: []` where missing
  - optionally validate `role` is one of `user|admin|moderator`
  - **not** auto-promote anyone to moderator (manual assignment after migration) Is that right?
- **Q16.** Do you already have specific users/datasets to seed in the script (e.g. `"alice" -> ["sas_cita_scans"]`), or should promotion stay fully manual post-migration?

### v0.5.1.0 - D2P Integration

- **Full D2P component suite**
  - `PassportToD2P` is partial
  - Extend respectively

### v0.5.2.0 - Design System Update

- **Full Design System Rewrite**
- Pointclouds, Additional Geometries
- resolving to designs made from d2p comps with joints?

### Manual Changes (Documentation)

#### **Components missing an image (14 total)**

These show the placeholder "Component Screenshot" box instead of a photo (`imagePath` unset on the gh-interface card):

1. `CSC_FetchTransmittedID`
2. `CSC_CreateUUID`
3. `CSC_PassportToD2P`
4. `CSC_AssignmentPoints`
5. `CSC_CreateReinforcement`
6. `CSC_ExtrusionProfile`
7. `CSC_RadialSignature`
8. `CSC_VisualizeEmbedding`
9. `CSC_ConvertGeoLocation`
10. `CSC_JSONKeys`
11. `CSC_JSONGetValue`
12. `CSC_ComputePCA`
13. `CSC_ComputeTSNE`
14. `CSC_GetDescriptor`

`PassportToD2P` and `CreateReinforcement` were added after the original list of 12.

**28 components** have images. Dedicated shots added for the identity/snapshot fetch cards:

- `CSC_ListIdentitySnapshots` -> `csc_listidentitysnapshots.png`
- `CSC_FetchAllSnapshots` -> `csc_fetchallsnapshots.png`
- `CSC_FetchSnapshot` -> `csc_fetchsnapshot.png`

Shared (not dedicated) images:

- `CSC_CreateComponentIdentity` / `CSC_CreateComponentSnapshot` -> `csc_createcomponent.jpg`
- `CSC_AddComponentIdentity` / `CSC_AddComponentSnapshot` -> `csc_addcomponent.jpg`
- `CSC_FetchReducedGeometry` / `CSC_FetchDetailedGeometry` -> `csc_fetchgeometry.jpg`

### Out of scope

- `upload_robot_scan.py` (legacy API) - will be touched at some point but not now
- Textured maps / GLB (post v0.5)
- UX polish (wizard + GH workshop parity)
