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
- **xeokit** (for later) --- open-source WebGL BIM viewer for whole IFC building models. In CSC it could show a
  piece in its donor building (floor, axis, facade highlighted) and check our own IFC export; replacing the
  three.js component viewer brings nothing for a single piece. Only once donor-building IFC models exist (no
  dataset has one so far), and only after clearing the licence: the xeokit SDK is AGPL-3.0, CSC is MIT, and
  AGPL code in the served web app would bind it to the AGPL (a commercial licence costs money). The IFC
  export does not need it. High effort.

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
- **Timber evidence: what does not map yet** (user 2026-10-16; analytical case for the thesis, not imported, decision
  8.149). Reference: the multimodal reclaimed timber dataset, <https://doi.org/10.5281/zenodo.17682666> (CC BY 4.0;
  56 reclaimed structural beams with CT volumes, visual grading, dynamic excitation, four-point bending, CM and FE
  models, a per-beam and per-zone summary table). Maps today: the identity (`IfcBeam`, `timber`, origin
  deinstallation without date or works, since species, building and age are not stated), a box or the CT surface
  mesh as geometry, and as archival claims density (also at 12 % moisture), moisture content and modulus of
  elasticity. Does not map: (a) quantities --- bending strength (`f_m`, `F_max`), a timber strength class or visual
  grade (INSTA 142, UNI 11119, prNS 3691-3; only `concrete_class` exists), static vs dynamic MOE as distinct
  quantities, the first eigenfrequency; (b) methods --- four-point bending (EN 408, with EN 384 adjustment),
  dynamic excitation, visual strength grading; the method set is concrete-oriented (rebound, cores, reinforcement);
  (c) values along the piece --- zone-wise results would need region positions along the beam axis or a profile
  result type; (d) fields --- CT volumes, density and stiffness fields, FE results have no representation beyond a
  link (a typed "field" attachment with units, grid and orientation would be the general answer). Future work: grill
  a timber method set (EN 408 / EN 384 / EN 338 / EN 14081 visual grading, dynamic MOE) with its quantities and
  tiers, then re-run this case as the before / after.

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
- Convenient and secure sign-in for the GH client (user 2026-10-13). Today the `Session` component takes username
  and password as Grasshopper inputs, so a Panel wired to them stores the password in clear in the `.gh` file (and
  in every copy shared with others). Goal: no secret in any input, panel or document, and no retyping per session.
  Candidate to grill: a device sign-in like `gh auth login`: the component shows a short code and opens the browser
  at a `/connect` page; the user, signed in on the website, approves the device; the component polls and receives a
  long-lived, revocable token for the GH client (scoped to the client, stored hashed on the server, last-used date,
  expiry with renewal, a list with revoke in Settings), exchanged for the short-lived JWT as now. On the machine the
  token lives in the Windows user's protected store (DPAPI / Credential Manager; macOS Keychain if Rhino for Mac
  matters), never in the document; a `Sign out` clears it. Fallbacks to weigh: a personal access token pasted once
  into a Rhino dialog (masked Eto field, not a GH input), or a masked password dialog per Rhino session. Until
  then: a warning in the component description and the GH docs not to wire a Panel to the password input.

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

## Brand

- A CSC logo (user 2026-10-10, moved out of 0.6.1.0 on 2026-10-12: not ready yet): a mark and a wordmark, light and
  dark, SVG source in `resources/brand/` with generated PNGs; the main brand in the sidebar, favicon and app icons,
  PDF passport, mails (a hosted PNG with alt text) and the Open Graph image; the lab's logo to the footer, About page
  and passport footer ("by DDU, TU Darmstadt"); GH icons later; repository licence with a note that the brand is not
  free to reuse. Details in 8.138 (a)--(d).

## Usage statistics

- Lightweight usage statistics for the maintainer (user 2026-10-10; moved out of 0.6.1.0 the same day). Built in,
  without cookies and without personal data, so no consent banner: the frontend sends small events to a backend
  route; the backend resolves the country from the IP with a local GeoIP file (DB-IP Lite, CC BY 4.0, or GeoLite2)
  and discards the IP; only daily counters are stored (day x event x page template x country x device class x signed
  in yes / no; referrer domain for page views), never raw events, user ids or full URLs. Events: page view by page
  template, search run (not the text), filter used, viewer opened, overlay switched, export (JSON-LD / PDF / CERO), QR
  scan, GH page / UserObject copied, registration and sign-in counts, draft saved, map opened. Signed-in users counted
  without a link to the account; admins not counted. Unique visitors per day at most, from a daily-rotating salted
  hash held in memory. Retention: daily counters 25 months, then monthly sums. Do Not Track / Global Privacy Control
  respected; an opt-out switch in the footer and Settings (stored locally as a necessary preference); the privacy page
  names the statistics, legitimate interest and the right to object; an admin page "Usage" with charts. Rejected:
  Plausible CE (ClickHouse, too heavy), Umami (one more service and database), hosted analytics (consent needed).

## Housekeeping

- **Transactions for record write plus change-log entry** (8.159 d, 2026-10-16): wrap each write and its `log_change` in a MongoDB transaction once the T4 refactor has put the writes in fewer places; needs a session through the write helpers, a one-node replica set for the test `mongod` and CI, and retry-safe route bodies (no mail or file writes inside `with_transaction`).

- ...
