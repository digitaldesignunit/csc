# Handoff --- CSC data model / evidence system design

**Update 2026-09-28 (end of day):** **0.5.1.0 is released and live** (tag `v0.5.1.0`, deployed on
Uberspace through the tag-driven release + approval-gated deploy pipeline, decision 8.5; server
converted to `~/csc/releases` + `current`, cron and `.bash_profile` moved, photo metadata
stripped). Python 3.13, client header (logged only), EXIF strip, local test environment and CI
are in place. **Next: P1 of `docs/adr/IMPLEMENTATION_PLAN_0.6.md` on a new branch `v-0.6.0.0` from
`main`.** Pending cleanup after a few good releases: the old server layout (deployment README,
step 7).

**P1 status: done and committed** (2026-09-30): vocab, document models, permission / lifecycle
predicates, invariant checker (I1--I28 + I3b), designs removed, client-header enforcement (8.11);
346 tests green. **P2 in progress (branch `v-0.6.0.0-P2`, 2026-09-30):** migrations
(`apps/catalog/migration06/`, `migrate_06.py`, `invoke rehearse` --- 0 invariant errors on 260916, idempotent) and
the read-only catch-up (0.6 read routes, 0.5 writes answer 503, frontend on generated 0.6 types; `invoke
dev-migrated` serves a migrated 260916 for the web app) are built; the user checked the web app. Grilled from that check: 8.22 (`ddu` test account), 8.23 (detail
levels Proxy / Preview / Reduced / Original), 8.24 (owners of every record, `beyond_debris`), 8.25
(moderators, `admin` test account), 8.26 (`ddu_aggregations` roles), 8.27 (no names
of people or accounts in committed files); nothing open. The 8.23 interface wording is built (viewer
detail selector, download groups, `/meshes/{i}/preview` with `/primitive` as alias). **Next:** user
review of P2, a rehearsal on the new dump, then P3. Before step 11b on production: fill the
maintainer's username into the untracked `.dev/reattribute_06.json`.

**Last session:** 2026-09-30 --- remaining review gaps grilled (8.12 verification owners, 8.13
attachments signed-in only, 8.15 frame closest to stored axes, 8.16 / 8.17 minor items incl.
"withdrawn" = tombstone outside the dataset), 8.14 invitations (new), full document review for
consistency. 2026-09-29: 8.6 HKS, `adr/` --> `docs/adr/`, agent-skill setup, review gaps 1--5
(8.7--8.11), P1. 2026-09-28: consistency pass (8.1--8.4), 0.5.1.0 released (8.5).
**Who:** the maintainer (TU Darmstadt DG) --- sole maintainer of CSC.

## 1. What this work is

CSC (Catalog of Second Chances) is a research-prototype catalog of reclaimed building components:
FastAPI + MongoDB Atlas backend (`src/backend`), Next.js frontend (`src/frontend`), Grasshopper
UserObjects (`grasshopper_userobjects_src`). Production: Uberspace 7, Python 3.13. Current
release 0.5.1.0 (live 2026-09-28); the design targets **0.6.0.0 on branch `v-0.6.0.0`**.

Threads merged into one spec:

1. **Evidence system** --- measurements (rebound hammer, cores) and non-instrumental claims as
   attributable, time-pinned records on a component identity (sessions 2026-09-10 --> 13).
2. **Generalised representation** --- proxies with deviation maps, derived shape class, property
   descriptors `{range, confidence, source}`. Precedent: M. Bernhard, *HYBREP* --- **cited, never
   used as a name**.
3. **CPR 2024/3110 / DPP alignment** --- CSC can *emit* a passport-shaped record (2026-09-12).
4. **Provenance, lifecycle, permissions, release path** (2026-09-23): `origin` / `exit`,
   lineage inheritance, tombstones, datasets as projects with memberships, snapshot freeze,
   client header, server-side derivation pipeline, materials vocabulary, Python 3.13.
5. **Entry surfaces, representation, scope cuts** (2026-09-24): web evidence + snapshot forms,
   attachments, GH bridge builders, capture context, reinforcement as evidence, condition grade,
   the frame, designs and virtual snapshots removed, photo metadata.

## 2. Where everything is

| file | role |
|---|---|
| `docs/adr/DATA_MODEL_SPEC.md` | **authoritative spec**, draft 5 (2026-09-30). section 0 reading guide ... section 10 CPR/DPP, Appendices A (evidence payloads, A.4 reinforcement layout), B (proxy primitives). section 9 = open questions (all struck through as decided). |
| `docs/adr/DESIGN_DECISIONS.md` | decision log: 1.x evidence, 2.x property fold, 3.x geometry, 4.x classification, 5.x CPR proposals, 6.x provenance / permissions / release, **7.x entry surfaces / representation / scope (2026-09-24)**, **8.x consistency pass + review gaps (2026-09-28 -- 30)**. |
| `CONTEXT.md` (repo root) | **glossary** (domain-modeling format): canonical terms + words to avoid. Created 2026-09-24. |
| `docs/adr/IMPLEMENTATION_PLAN_0.6.md` | **phased plan**: P0 = 0.5.1.0, P1--P9 = 0.6 (foundations --> migrations + rehearsal --> permissions / lifecycle --> provenance --> geometry runner --> evidence --> web --> GH bridge --> cutover); test strategy; Q1--Q3 decided |
| `docs/adr/HANDOFF.md` | this file |
| `AGENTS.md`, `docs/agents/` | agent-skill config: GitHub issues, triage labels, domain-doc rules (2026-09-29) |
| `future_implementation/MEASUREMENTS_SPEC.md` | original measurement spec --- superseded, kept for domain research and standards sources. Gitignored. |
| `future_implementation/IMPLEMENTATION_PLAN_V0-5+.md` | older plan; its 0.5.0.2 moderator section is **superseded by 6.5** |
| `reference/pdf/Bernhard_HYBREP.pdf`, `reference/pdf/CPR_2024_3110.pdf` | sources. Gitignored. |
| `mongodb_collections_local/260916/` | newest local dump (identities, snapshots, map cache --- **no designs**) |
| `D:\01_PROJECT_WORKDATA\260916_CSC_ASSETS` | files for that dump (meshes, point clouds, photos, previews) |

`docs/adr/` (moved from `adr/` 2026-09-29) and `CONTEXT.md` are tracked in git.

## 3. Resume here

**A. Grilling --- done.** HANDOFF items 1--3 of 2026-09-23 closed by 7.1--7.13 (A.3 "designs x new
lifecycle" dissolved: designs are removed, 7.11).

**A2. Review gaps (external review, checked 2026-09-29) --- all closed 2026-09-30 (8.7--8.17); next is P2:**
before P1: ~~(1) stage-order loop~~ (decided 8.7) shape class <-> proxies (stage 2 needs `boxscore` from stage 4);
~~(2) when a split takes effect~~ (decided 8.8) (parent `exit` set by a child whose v0 is still a draft; cross-dataset
`exit` without `moderator(parent D)`); ~~(3) identity has no draft state~~ (decided 8.9) (contributor cannot fix a
typo; visibility of an identity whose only snapshot is a draft; evidence on it); ~~(4) v0
`effective_from = created`~~ (decided 8.10) vs. valid time (`origin.at`), and what the snapshot fold does with
`before_first` / `after_exit` evidence. Before P3 / P6: ~~(5) header enforcement vs. `/id/{uuid}` and
anonymous API readers~~ (decided 8.11); ~~(6) who sets `self_attested`, four-eyes for `reviewed`, typed-in
accreditation~~ (decided 8.12, I27 in code); ~~(7) attachments on public pieces vs. GDPR (redaction does not
reach files)~~ (decided 8.13). New, not from the review: non-TU registration by email-bound invitation
(decided 8.14, plan P3). Before
P5: ~~(8) frame sign rule + tie-break tolerance for near-equal extents~~ (decided 8.15). Minor: ~~(a) withdrawing the current
snapshot without replacement vs. I3b~~ (decided 8.17: tombstone outside the dataset, automatic fallback); ~~(b) two pending supersessions of one record (I14); (c) evidence on
exited / withdrawn identities; (d) reinforcement layouts after a correction in new coordinates~~ (decided 8.16,
I14 extension + I28 in code).
(The review's CORS side note on item 5 is wrong: browser calls go through `/api/backend`, which
adds the header; CORS already allows all headers.)

**B. Claude's work, reviewed by user:**
1. ~~**Spec consistency pass.**~~ **Done 2026-09-28** (draft 4, decisions 8.1--8.4). Known items: section 0 / section 1 still describe the pre-6.x model (no datasets,
   origin / exit, capture, frame); "measurement" wording where "evidence" is meant (1.6); the fold
   pseudo-code (section 4.4) reads only `summary`, although `derived[]` entries with a different quantity
   are meant to feed the fold (`compressive_strength_in_situ`); section 4.3 prose still says "PCA" in
   places; section 7 route list vs. 7.1--7.11 (designs gone, `/evidence/bulk`, attachments); cross-refs.
2. ~~**Verify the 5 LoW codes.**~~ **Done** --- all exist; fit notes in section 2.10 (source: AVV Anlage).
3. ~~**Phased implementation plan**~~ **Drafted** --> `docs/adr/IMPLEMENTATION_PLAN_0.6.md`. Original brief: work breakdown, order, tests, migration
   rehearsal on 260916 (steps 1--14). Suggested spine: vocab + models --> datasets / permissions -->
   status lifecycle / tombstones / freeze --> origin / exit / lineage --> geometry runner (frame 7.10,
   shape_class) --> capture migration (7.7) --> proxies --> evidence + fold + attachments (7.3) +
   reinforcement layout (7.8) --> migrations rehearsed --> frontend (snapshot form 7.5, evidence form
   7.1 / 7.4, moderation, `/admin` datasets) --> GH bridge (builders 7.6, `ReinforcementLayout` +
   `AddEvidence`).

**C. Shipped:** **0.5.1.0** (tag `v0.5.1.0`, live 2026-09-28): `X-CSC-Client` header in all GH
UserObjects + backend logging; Python 3.13 with `constraints.txt` (glibc-2.17 ceiling); photo-metadata
strip (7.13, incl. cleanup of stored photos); local test environment, CI, release + deploy pipeline (8.5).

**Small confirmations:** answered 2026-09-28 --- ZirKuS bars `basis: drawing`; 2024-07-24 applies to
all 16 `dbu_zirkus` pieces.

## 4. Decisions that are locked (do not re-ask)

Full list with consequences in `DESIGN_DECISIONS.md`. Sessions 1--2 (1.x--4.x): documentation of
record; snapshot context recomputed; atomic evidence, range+n; destructive test = event;
`component_evidence`; `status` + `verification`; supersede-don't-edit; derived property fold
(tiers, per-quantity scope, x0.8 inheritance); `condition` dropped; `geometry.proxies[]`;
`original_function` (IFC names) + derived `shape_class`; `regions[]` slot only.

Session 3 (2026-09-23): 6.1 `origin` ; 6.2 server-side lineage inheritance ; 6.3 `exit` +
re-entry ; 6.4 tombstones ; 6.5 datasets as projects, roles `{contributor, reviewer, moderator}` ;
6.6 published snapshots freeze ; 6.7 release path, header enforced, no aliases ; 6.8 CPR triage ;
6.9 raw-UUID tags + `/id/{uuid}` ; 6.10 materials + LoW class + trade name ; 6.11 no new geometry
dependency ; 6.12 Python 3.13 ; 6.13 small items ; 6.14 all derivation server-side ; 6.15
`complexity` derived + overridable.

Session 4 (2026-09-24):
- **7.1** Evidence enters through one web form from the component page (phone after scan, or
  desktop): fan-out, repeat-from-last, apply-to-several-pieces; "?" popovers with help text from
  the backend; `POST /evidence/bulk`. No sheet, no CSV import, no GH evidence components in 0.6.
- **7.2** No campaign concept; `campaign_id` dropped (study = dataset, occasion = the record).
- **7.3** Attachments: one copy per record (hard-linked), `attachments[]` with sha256 + uploader;
  add-only after publish, removal = moderator + tombstone entry.
- **7.4** Inspection photos are evidence attachments, per observation --- not snapshot photos.
- **7.5** Web snapshot form from four places: new component, cut from..., record new state,
  correct. Draft --> submit. Web mesh / point-cloud upload deferred (planned).
- **7.6** GH bridge builder components `Actor`, `Origin`, `IdentityMetadata`,
  `SnapshotMetadata` (JSON fragments of the API payload); Create components ~8 inputs.
- **7.7** Per-snapshot `capture` block (coordinate system, labelled markers, fixture meshes); marker points
  and the robot gripper mesh leave `geometry`.
- **7.8** Reinforcement is evidence: `reinforcement_layout`, one record per source, tier by
  basis; the bridge ships `ReinforcementLayout` + generic `AddEvidence`.
- **7.9** `condition_grade` = first-class overall visual grade (3 good ... 0 unusable as is);
  0.5 default grades not migrated; badge = grade, else 3 - worst finding.
- **7.10** The frame (`frame` + `bbx`, renamed from `pca_frame`) is its own derived field:
  minimum-volume box; longest --> X, middle --> Y, shortest --> Z; linear `IfcColumn` stands (Z).
  Matrix section 6 reviewed.
- **7.11** Designs removed from CSC (collection archived at cutover); `exit.design_id` and the
  snapshot `iframe` go. Evaluation happens in GH; published designs belong in tools like Speckle.
- **7.12** Virtual snapshots removed.
- **7.13** Photo EXIF: strip GPS / owner / serial, keep orientation, capture time, make / model.

Sessions 2026-09-28 / 29: 8.1--8.4 consistency pass (`frame` = canonical orientation only; outranked;
one snapshot PATCH; pass fixes); 8.5 monorepo release model; **8.6 HKS on a 3000-point even surface
sample with the point-cloud Laplacian** (not the mesh, not the convex hull; fixed time grid) --- plan P5.
8.7 hull scores in stage 1 + input fingerprints; 8.8 split on the child's first publish (two
moderators); 8.9 unpublished identity; 8.10 v0 starts at `origin.at`; 8.11 header optional for
anonymous GETs, "not public" page.

Session 2026-09-30: 8.12 verification owners (recorder self-attests, four eyes for `reviewed` /
`accredited`, no admin exception, I27); 8.13 attachment files signed-in only, GDPR worklist; 8.14
email-bound invitations; 8.15 frame = valid frame closest to the stored axes; 8.16 one open
correction, I28, positioned evidence stays on its snapshot; 8.17 withdrawn = full for D, tombstone
outside, automatic current-snapshot fallback; 8.18 pending records: moderator edits, author recalls; 8.19 archived out-of-circulation gaps resolve as `after_exit`; 8.20 member editor by email (exact for moderators, search for admins); 8.21 admin user list filters (dataset, role, state, invited).

## 5. Facts about the data (dump 260916)

697 identities / **701 snapshots** --- 4 identities have a v1 (3 `schoenes_neues_feld`, 1
`dbu_zirkus`); all `validated: true`, none virtual. Datasets: `mineral_composite_panels` 477,
`sas_cita_scans` 71 (0.6: `beyond_debris`, 8.24), `ddu_build_with_debris` 70, `ddu_aggregations` 50, `dbu_zirkus` 16,
`spa_example_data` 9, `schoenes_neues_feld` 4. 45 split children / 37 parents. 42 consumed. 700 of
701 snapshots written by the shared `ddu` account. `processes` empty and `assembly` false
everywhere. `complexity` and `condition` are batch defaults (condition `2` on 698 of 701; only
`schoenes_neues_feld` varies). **All 70 `ddu_build_with_debris` snapshots** hold the robot rig
inside `geometry`: 4 constant blue markers (+/-120 mm cross = gripper marker plane), green markers on
the stone (a few pieces), and the gripper as `meshes[1]` with PLYs. **Reinforcements:** 1 snapshot
(`dbu_zirkus`, 35 bars, BSt III dia. 8). **Photos:** 3 of 8 in the assets folder carry GPS. The web
wizard's `canonicalizeBoxAxesMm` already encodes the 7.10 axis convention. GH tooltips still say
dataset `mineral_composite_sheets` (the data says `mineral_composite_panels`) --- fixed by the GH
bridge rewrite; old migration scripts are left as they are (user).

## 6. Caveats

- 0.6 code: P1 only (models, predicates, invariant checker); no 0.6 migrations exist yet (P2).
- Number of designs in production unknown (not in the dumps) --- archived at cutover (section 8 step 13).
- CPR analysis is alignment, not compliance (delegated act under Art 75(1) does not exist yet).
  EN 18219/18220/18221/18222 only needed for deferred items (identifiers, export).
- DIN SPEC 91484 not obtained.
- Shape-class and complexity thresholds are guesses until the tuning script runs.
- U7 = CentOS 7 / glibc 2.17: numpy <= 2.2.6, scipy <= 1.16.3, scikit-learn <= 1.7.2 on cp313.
