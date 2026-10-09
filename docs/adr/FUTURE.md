# Future ideas

Loose ideas for after 0.6. Nothing here is decided or scheduled; an idea becomes work only
through a grilling session and a numbered entry in `DESIGN_DECISIONS.md`. Additive items the 0.6
triage rule (decision 6.8) deferred are listed in `DATA_MODEL_SPEC.md` (search **deferred**) and
are not repeated here.

Started 2026-10-02 from the untracked 0.5 `FUTURE.md` notes, the retired 0.5
measurements draft and the open items of the archived 0.5 plan (`archive/IMPLEMENTATION_PLAN_0.5.md`).

---

## Environmental data / LCA

The value proposition of second-chance components is environmental, so this is the most obvious
gap.

- **Oekobaudat** --- German national LCA database, free, REST API. Embodied carbon / GWP per
  material class could fill the `env_*` quantities (spec section 10.3, EN 15804 indicator codes).
- **ecoinvent** --- the reference LCA database, commercial. Not integrable directly; at most a
  link from a material to an ecoinvent UUID.
- **openLCA** --- open-source LCA software with an IPC API; could compute an LCA per design built
  from fetched catalog data (designs live outside CSC, decision 7.11).
- Cheapest start: material-class lookup tables feeding a `calculated` source tier (spec 10.5).

## BIM / IFC

- **IFC export via IfcOpenShell** --- proxies map to `IfcExtrudedAreaSolid` / `IfcTriangulatedFaceSet`,
  properties to a PSet (spec section 10.4). Unlocks professional AEC workflows. *(On the 0.6.0.x backlog since
  2026-10-08, plan P12 "Backlog after P12"; to grill.)*
- **xeokit** --- open-source WebGL BIM viewer; could replace or augment the component viewer,
  with IFC support. High effort, high visual impact.

## Geometry search and processing

- **Similarity search** over the stored descriptors (scores, radial signature, HKS). The missing
  piece is a search endpoint; candidates are Faiss (local) or a vector index in MongoDB. Lets a
  designer find geometrically similar pieces.
- **Radial signature matching** must compare across circular shifts, or the descriptor needs a
  rotation-invariant form: `rest_position` picks no stable rotation for symmetric outlines (a mesh
  and a point cloud of the same L-panel landed a quarter turn apart). Changing the descriptor
  invalidates every stored signature.
- **Open3D** --- mesh quality analysis, better preprocessing for the geometry runner.

## Component map

- **Descriptor combinations chosen by the user** (user 2026-10-07): PCA computed live for any ticked combination
  (radial signature at 16 / 32 / 64 / 128, the four shape scalars, bounding-box size and proportions, complexity);
  measured on a laptop: 3 ms (1,500 x 4) to 0.4 s (1,500 x 496), so fine per request. UMAP only for a few fixed
  presets precomputed in `component_map_cache` (5--11 s warm per layout, about 30 s for the first call per process
  while numba compiles; 2--3 times that on Uberspace); optionally a signed-in "Compute UMAP" as a background job,
  cached per combination and scope, rate-limited. Dataset or material as embedding dimensions not recommended (they
  dominate the distances and split the map by category); "Colour by" plus the filter bar answers that, a weight
  slider off by default if ever wanted.

## Evidence and analytics

- **Analytics page:** size distribution (bounding box) per dataset; compressive strength
  distribution per dataset / material class; **rebound-vs-core scatter** per site, which is the
  EN 13791 comparative-testing workflow --- a site-specific correlation curve is something a
  component catalog could offer that few tools do.
- **Batch entry:** a coring campaign yields 6--12 cores across several pieces in one day. CSV or
  lab-report import, a spreadsheet-style entry sheet (both excluded from 0.6, decision 7.1).
- **EN 13791 test regions** --- group similar pieces of one concrete into a test region and
  derive its characteristic in-situ strength and the site correlation from the paired
  rebound / core records (8.42). Regions are a later judgment over stored records, so nothing
  is lost by waiting.
- **ASTM variants** of rebound (C805) and cores (C42, C39) as additional methods with their own
  rules, once a user outside Europe needs them and the texts are at hand (8.40).
- **Grasshopper evidence components** (create / add / fetch evidence), after the web form.
- **Further evidence methods** (UPV, carbonation, cover meter, half-cell, pull-off, moisture,
  timber grading, steel coupons) --- one `EvidenceMethodSpec` each, list in spec section 2.5.
- **DIN SPEC 91484** cross-check against the identity record and Appendix A once the standard is
  obtained.

## Moderation

- **Four-eyes per dataset** (8.120): an optional dataset setting under which a moderator may not publish their own
  submission; off by default, since datasets with one moderator would block.

## Batches and reuse marketplaces

- **Reservations with a count** on a batch (`reservations: [{user_id, quantity, at}]`, sum <=
  `remaining`): 0.6 reserves whole identities only, and part of a batch is held by drawing a
  sub-batch (8.105). Needs a multi-holder reservation model, its API, web and GH paths.
- **Amounts without a piece count** (areas, running metres: insulation, perforated sheet, cable
  trays) are not batches and were left out of the external catalogue import (8.105, 8.108).
- **`env_*` quantities from catalogue CO2 figures**: the catalogue values sit as text in document
  claims (8.106) until the environmental quantities exist; a correction can then turn them into
  values.

## Material knowledge

- **Wikidata** --- link materials to Q-IDs for richer metadata and interoperability.
- **Materials Project API** --- engineering properties (density, thermal conductivity); more
  structural than architectural.

## Grasshopper interface

- Add geometry (a mesh or point cloud) to an existing snapshot from Grasshopper.
- Full D2P component suite; `PassportToD2P` is partial.
- gh-interface cards: 14 components still show the placeholder image (list in the archived 0.5
  plan); the `CSC_RadialSignature` card should say that reproducing a non-panel descriptor needs
  `RestPositionAlign=False` plus the PCA-plane section curve.

## Linked data

- **A dereferenceable vocabulary page** for the JSON-LD `@vocab` (`{FRONTEND_URL}/vocab/v1#`, 8.117 b): today a
  namespace only; a page per CSC term (label, definition from `CONTEXT.md`, the mapping columns) would make the
  terms resolvable. The IFC-OWL namespace as a second IFC mapping next to the bSDD class identifiers (8.117 a).

## Agent access (MCP)

- **A read-only MCP server over the API** (after the cutover, 0.6.x; user 2026-10-05): tools for
  search with filters (function, material, size, circulation, condition), the component passport,
  properties and evidence, lineage, descriptor neighbours (the map) and links to geometry files ---
  never geometry itself through MCP. Designers ask in plain language; with a Rhino / Grasshopper MCP
  server an agent can match pieces to a design and place them. Same access tiers as the API: per-user
  tokens, the public tier without people for anonymous callers (8.101). Writes at most as drafts that
  go through moderation; never publish, withdraw or reserve. A thin server (S--M), e.g. Streamable
  HTTP mounted next to FastAPI on Uberspace (one more supervisord / web backend route), or a local
  stdio server that calls the public API.

## Housekeeping

- ...
