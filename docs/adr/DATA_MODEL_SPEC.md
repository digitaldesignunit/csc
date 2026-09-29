# CSC Data Model Specification --- v0.6 (draft 4)

**Status:** draft 4, 2026-09-28 --- consistency pass after grilling closed (decisions 1.1--7.13,
`docs/adr/DESIGN_DECISIONS.md`). Draft 3 2026-09-24 (7.x), draft 2 2026-09-23 (6.x), first draft
2026-09-12. Glossary: `CONTEXT.md` (repo root) --- field names follow its terms. Supersedes
`future_implementation/MEASUREMENTS_SPEC.md` (kept for its domain research and sources). Nothing
here is open; items marked **deferred** are out of 0.6 by the triage rule (6.8).
**Precedent:** the hybrid-representation ideas here --- proxies that keep their deviation from
the scan, `{range, confidence, source}` property descriptors, resolution following design
relevance --- follow M. Bernhard, *HYBREP: A Hybrid Representation Framework for Computational
Design with Reclaimed Building Elements* (DBT, ETH Zuerich; `reference/pdf/Bernhard_HYBREP.pdf`).
**Regulatory reference:** Regulation (EU) 2024/3110 (recast CPR). Every field it touches carries a
`CPR:` note pointing at the article/annex; the full analysis is section 10, the wider EU passport
landscape section 10.6.
CSC does not adopt the name; it adopts the ideas and cites the paper.
**Target:** 0.6.0.0 on branch `v-0.6.0.0` (decision 6.7); release path section 8.0.
**Calibration:** research prototype. Correctness and best practice over migration cost.

---

## 0. Reading guide

| Section | Contains |
|---|---|
| 1 | Conceptual model --- the entities and the four rules that bind them |
| 2 | Vocabularies --- every controlled list, with authority and extension policy |
| 3 | Documents --- field-by-field for each collection (identities, snapshots, evidence, datasets, users, materials), plus on-disk companions |
| 4 | Derivations --- the pure functions that compute derived fields |
| 5 | Invariants --- what the backend must reject |
| 6 | Type x representation matrix |
| 7 | API surface |
| 8 | Migration from 0.5 |
| 9 | Decided questions (index into the decision log) |
| 10 | CPR 2024/3110 & DPP alignment |
| A | Evidence payloads: rebound hammer, core compression, non-instrumental kinds, reinforcement layout |
| B | Proxy primitive definitions: params, faces, UV |

---

## 1. Conceptual model

```
Dataset ----------------------------- "which project" --- membership, roles, visibility (section 3.6)
  |
  +-1:N-> ComponentIdentity ----------- "which physical piece"
            |  original_function (IFC name), material (+ class, trade name)
            |  origin / exit / past_cycles         how it entered and left circulation (section 3.1.1, section 3.1.3)
            |  parent_identities[] + inherited_fields   split / merge lineage (section 3.1.2)
            |  properties {...}                      DERIVED: identity-scoped quantities (section 4.4)
            |  withdrawn                           record-level tombstone (section 3.1.4)
            |
            +-1:N-> ComponentSnapshot ----- "what state, what shape, from when"
            |         status, supersedes           moderation lifecycle; corrections (section 3.2.2)
            |         effective_from               valid-time start of this state (section 4.1)
            |         geometry                     meshes[] / point_clouds[] / proxies[] --- the component only
            |           proxies[].deviation_maps   per-face images (files)
            |         capture                      how the geometry was recorded: coordinates, markers, fixtures (section 3.2.3)
            |         frame + bbx                  DERIVED standard orientation and size (section 4.3 stage 1)
            |         shape_class, complexity      DERIVED, overridable (section 4.2, section 4.2b)
            |         descriptors, properties {...}  DERIVED (runner stage 4; as-of fold section 4.4)
            |
            +-1:N-> Evidence -------------- "what was observed or claimed, by whom, when"
                      method (discriminator)       rebound_hammer | core_compression | ... | reinforcement_layout
                      observed_at / sampled_at     two valid times (section 3.3)
                      position                     optional, in ONE snapshot's coordinates
                      summary (+ derived[])        normalised results --- the fold input
                      payload, attachments[]       method-specific, typed; files
                      status + verification        moderation vs. epistemic (section 3.3.3)

Materials (section 2.10) and users (section 3.7) are reference collections. No Design entity --- designs left
CSC (decision 7.11); the reuse function lives in design tools.
```

Four rules:

1. **Identity is the anchor.** Evidence and properties attach to the identity. Geometry attaches
   to snapshots. Nothing attaches to "the component" in the abstract.
2. **Derived fields are never authored.** `properties`, `frame` / `bbx`, `shape_class`,
   `complexity`, `material_class`, fitted `proxies[]`, `descriptors`, inherited fields, snapshot
   context --- all computed by a named pure function (or server-side propagation) from stored
   inputs. Overrides, where allowed, are recorded as overrides (`*_source: assigned`,
   `inherited_fields` minus the field).
3. **Raw and derived stay distinct.** A rebound median is measured; a strength inferred from it is
   derived and names its model. A property's `source` tier says which kind of evidence produced it.
4. **Time is bitemporal-lite.** `created`/`lastmodified` are transaction time (when the row
   changed). `effective_from`, `observed_at`, `sampled_at` are valid time (when reality changed).
   Never conflate them.

---

## 2. Vocabularies

Extension policy for every vocabulary: values live in code (`apps/catalog/vocab.py`, replacing
`catalog_meta_vocab.py` for these lists), each with a display label. A vocabulary change is a code
change with a migration if it renames. **Two exceptions live in collections** because they grow
with the projects, not with the code: `datasets` (section 3.6) and `materials` (section 2.10, seeded from
code, admin-extensible). The 0.5 `merge_additional_with_catalog` pattern (DB distinct values union
code list) is **removed**.

### 2.1 `original_function` (identity)

IFC element-class **names only**. No IFC structure is imported.

| value | label | notes |
|---|---|---|
| `IfcBeam` | Beam | |
| `IfcColumn` | Column | |
| `IfcSlab` | Slab | horizontal planar, structural |
| `IfcPlate` | Plate / Panel | non-structural planar; the 527 corian panels |
| `IfcWall` | Wall | |
| `IfcMember` | Member | linear, function not beam/column (bracing, purlin) |
| `IfcPipeSegment` | Pipe | |
| `IfcFooting` | Footing | |
| `IfcDiscreteAccessory` | Accessory / Connector | |
| `IfcBuildingElementPart` | Element part (masonry unit, ...) | IFC 4.3.2: component used to compose a building element. A whole reclaimed brick/block (decision 6.13); brick *rubble* stays `CscDebris` |
| `IfcBuildingElementProxy` | Unknown | function not known |
| `CscDebris` | Debris | CSC extension: no prior function as a discrete element (rubble, aggregate) |

Semantics: **what the piece was** in its previous life. The reuse function is a design decision
made in design tools outside CSC (decision 7.11) and is never recorded here.

> CPR: the *declared use* (Art 3(22), Annex V 1(c)) is fixed by the manufacturer at placing on
> the market --- i.e. at export/design time, never on the identity. `original_function` feeds the
> Annex VII product family (section 10.3) and the BIM interoperability requirement (Art 75(2)(a)).

### 2.2 `shape_class` (snapshot, derived)

| value | definition | typical `original_function` |
|---|---|---|
| `linear` | one dominant extent | IfcBeam, IfcColumn, IfcMember, IfcPipeSegment |
| `planar` | two dominant extents | IfcPlate, IfcSlab, IfcWall |
| `block` | three comparable extents, box-like | bricks, blocks, footings |
| `irregular` | no primitive fits | CscDebris, stone |
| `composite` | several distinct bodies / branching | IfcDiscreteAccessory, assemblies |

`composite` cannot be derived; it is always assigned.

### 2.3 Proxy primitives

`box`, `prism`, `cylinder`, `hull`. Definitions in Appendix B.

### 2.4 Fit methods

`authored` (human-modelled, no source), `obb` (minimum-volume oriented box, `trimesh`; was `pca_obb`, decision 7.10), `ransac`,
`lsq` (least-squares refinement), `hull` (deterministic convex hull).

### 2.5 Evidence methods and source tiers

| `method` | tier | instrument? | payload |
|---|---|---|---|
| `rebound_hammer` | `ndt` | yes | A.1 |
| `core_compression` | `destructive` | yes | A.2 |
| `archival_document` | `archival` | no | A.3 |
| `visual_inspection` | `visual` | no | A.3 |
| `era_heuristic` | `heuristic` | no | A.3 |
| `manufacturer_datasheet` | `archival` | no | A.3 |
| `reinforcement_layout` | by `basis`: `drawing` --> `archival`, `scan` --> `ndt`, `exposed` --> `visual` | --- | A.4 (decision 7.8) |

Future instrumental methods (UPV EN 12504-4, carbonation EN 14630, cover meter, half-cell,
pull-off, moisture) are one `EvidenceMethodSpec` each (section 4.5).

Tier base confidences (policy constants, `vocab.py`):

| tier | base |
|---|---|
| `destructive` | 0.90 |
| `ndt` | 0.60 |
| `archival` | 0.40 |
| `visual` | 0.30 |
| `heuristic` | 0.20 |
| `inherited` | parent confidence x `INHERIT_K` (0.80) |

### 2.6 Quantities

Each quantity carries: canonical unit (UCUM), value kind, **scope**, and its own tier ranking.

**Scope** decides which fold target receives it (section 4.4): `identity` --- a fact about the physical
material, true regardless of state (folded from *all* published evidence into
`identity.properties`); `snapshot` --- a fact about one state (folded from evidence whose resolved
context is that snapshot into `snapshot.properties`).

| `quantity` | unit | kind | scope | tier ranking (highest first) |
|---|---|---|---|---|
| `compressive_strength` | `MPa` | scalar | identity | destructive, ndt, archival, visual, heuristic |
| `compressive_strength_in_situ` | `MPa` | scalar | identity | destructive, ndt, archival, heuristic |
| `rebound_number` | `1` | scalar | identity | ndt |
| `q_value` | `1` | scalar | identity | ndt |
| `density` | `kg/m3` | scalar | identity | destructive, ndt, archival, heuristic |
| `rebar_diameter` | `mm` | scalar | identity | destructive, ndt, archival, visual, heuristic |
| `rebar_spec` | --- | categorical | identity | destructive, archival, ndt, heuristic |
| `concrete_class` | --- | categorical | identity | destructive, archival, ndt, heuristic |
| `cover_depth` | `mm` | scalar | identity | ndt, destructive, archival |
| `mass` | `kg` | scalar | **snapshot** | destructive, ndt, heuristic |
| `carbonation_depth` | `mm` | scalar | snapshot | destructive, ndt, visual |
| `spalling` | --- | ordinal 0--3, severity | snapshot | visual, ndt --- applies to mineral |
| `cracking` | --- | ordinal 0--3, severity | snapshot | visual, ndt --- applies to mineral, polymer, bio-based, bituminous |
| `corrosion` | --- | ordinal 0--3, severity | snapshot | visual, ndt --- applies to metal, reinforced mineral |
| `moisture_content` | `%` | scalar | snapshot | ndt, destructive |
| `condition_grade` | --- | ordinal 0--3, **3 = good** | snapshot | visual --- **overall visual grade, any material** (decision 7.9): 3 good, 2 average, 1 poor, 0 unusable as is. The wizard's optional inspection step records only this. |

**Findings vs. overall grade (decision 7.9).** Findings (`spalling`, `cracking`, `corrosion`) are
severities, 0 none ... 3 severe; the inspection form offers only those whose material group matches
the piece (section 2.10 `group`). `condition_grade` keeps the 0.5 direction (higher = better). The UI
**condition badge** = the snapshot's folded `condition_grade` if present, else `3 - max(finding
severity)`; no inspection --> "not assessed". More material-specific findings (chipped edges,
surface wear, rot, residue) are additive vocabulary rows --> deferred (6.8).

`mass` is **snapshot-scoped** (decision 6.13): moisture, damage, removed fixings and core holes
change mass without creating a new identity (a core hole creates no snapshot either, 1.5 --- the
as-of fold picks up post-coring weighings by time). `density` stays identity-scoped (material).

Units are UCUM codes, stored as-entered plus canonical (server converts).

> CPR: each quantity is a candidate *essential characteristic* (Art 3(7), Annex I basic
> requirements --- e.g. compressive strength --> Annex I 1 structural integrity). The 19 `env_*`
> quantities proposed in section 10.3 are Annex II verbatim, which is EN 15804+A2's 13 core + 6
> additional indicators (section 10.6). A future column `cpr_essential_characteristic` carries the
> mapping (section 10.5 item 5).

### 2.7 Timestamp precision

`exact | day | month | year | unknown` --- extends the existing `ALLOWED_MANUFACTURED_PRECISIONS`
with `day`. (CPR: the CE mark carries only the *year* of deinstallation, Art 18(2)(a) --- `year`
precision is a legitimate, expected value for `origin.at`.) Applies to `manufactured_at`,
`origin.at`, `exit.at`, `effective_from`, `observed_at`, `sampled_at`.

### 2.8 `origin.kind` (identity)

How the piece entered circulation (section 3.1.1). The distinction matters regulatorily: only a
deinstalled piece can be a CPR *used product*; demolition output is waste until end-of-waste;
production residue is a by-product question, not a reuse one.

| value | label | definition | regulatory reading |
|---|---|---|---|
| `deinstallation` | Deinstalled | removed from a construction work in which it had been installed | CPR *used product* candidate, Art 3(20); `origin` = Annex V 1(h) |
| `demolition` | Recovered from demolition | recovered from demolition output, not individually deinstalled | waste until end-of-waste, WFD 2008/98/EC Art 6; not a CPR used product until then |
| `offcut` | Production offcut | residue of a fabrication process, never installed (e.g. the Corian offcuts from Rosskopf + Partner) | WFD Art 5 *by-product* candidate; never a used product (Art 3(20) needs prior installation) |
| `surplus` | Surplus | unused whole product: overstock, returns, site leftovers; never installed | a new product, not a used one |
| `unknown` | Unknown | provenance not recorded | none claimable |

### 2.9 `exit.kind` (identity)

How the piece left circulation (section 3.1.3).

| value | label | physical piece | terminal? | notes |
|---|---|---|---|---|
| `split` | Split | ceased to exist as this identity | yes | server-set on child creation; children via lineage |
| `merged` | Merged | ceased to exist as this identity | yes | server-set when a child has >1 parent |
| `installed` | Installed | exists, in a construction work | no --- re-entry allowed | reuse accomplished; `construction_work` optional (where it went). A later deinstallation starts a new CPR life (Art 3(53)) |
| `recycled` | Recycled | material recovered, not the piece | yes | crushed to aggregate, melted, ... |
| `disposed` | Disposed | landfilled / waste | yes | |
| `returned` | Returned | exists, left CSC custody | no | back to owner / supplier |
| `lost` | Lost | unknown | no | whereabouts not recorded |

---

### 2.10 `material` (identity --- decision 6.10)

Three fields on the identity:

```jsonc
"material": "mineral_composite",          // FK --> materials._id; generic name, never a brand
"material_class": "17 02 03",             // DERIVED from the material's default class; overridable
"material_class_source": "derived" | "assigned",
"trade_name": "Corian" | null             // free text: brand / product name
```

**External axis: EU List of Waste (LoW), chapter 17 "Construction and demolition wastes"**
(Commission Decision 2000/532/EC as amended by 2014/955/EU). Chosen over Uniclass 2015 Ma
(v1.1, July 2026), which has no current codes for fired clay/ceramics, no autoclaved aerated
concrete, no acrylic/solid surface, and wood only by species. LoW is EU law, is what EU
pre-demolition audits record, links to `origin.kind: demolition` / end-of-waste (WFD), and matches
the material groups of Level(s) 2.1. It is a *class*; the specific material is CSC's. Uniclass is
kept as an optional second mapping column where a current code exists.

**Why overridable:** LoW 17 01 separates by product form, not only material (fired clay: bricks
17 01 02, roof tiles 17 01 03). The material's `default_class` is the common case; a moderator
assigns the other (`material_class_source: assigned`, never overwritten by recompute).

**Hazardous entries (`*`) are never derived** from the material: 17 03 01* (asphalt with coal
tar), 17 02 04* (treated wood), 17 06 05* (asbestos), 17 01 06*, 17 06 03*, ... require evidence
(PAH test, treatment class, asbestos survey). `material_class` is the non-hazardous default until
such evidence exists; the evidence quantities that switch it are **deferred** (additive, 6.8).

**Storage:** a `materials` collection `{_id, label, group, default_class, uniclass, notes}`,
seeded from code (`vocab.py`), extendable by admin via `/admin` --- every entry must carry a
`default_class`. This ends the merge-vocab pattern entirely (section 2 extension policy).

Seed list. **Codes verified 2026-09-28** against chapter 17 as transposed verbatim by the German
AVV (Anlage, gesetze-im-internet.de/avv; EUR-Lex blocks scripted access): every code below exists
with the wording assumed. The LoW classifies *waste streams*, so for five materials the fit is a
judgement, noted in the table --- all are overridable (`material_class_source: assigned`).

| `_id` | label | group | `default_class` (LoW) | Uniclass |
|---|---|---|---|---|
| `concrete` | Concrete | mineral | 17 01 01 | Ma_40_19 |
| `autoclaved_aerated_concrete` | Autoclaved aerated concrete | mineral | 17 01 01 (AAC is a concrete, EN 771-4; some disposers demand 17 01 07 for its sulfate content) | --- |
| `fired_clay` | Fired clay (brick, roof tile) | mineral | 17 01 02 (roof tile --> assign 17 01 03) | --- |
| `calcium_silicate` | Calcium silicate (sand-lime) | mineral | 17 01 02 (EN wording "bricks" covers calcium-silicate bricks; German "Ziegel" reads as fired clay --- assign 17 01 07 where local practice requires) | --- |
| `ceramic` | Ceramic (tiles, sanitary ware) | mineral | 17 01 03 | --- |
| `natural_stone` | Natural stone | mineral | 17 05 04 ("soil and stones" --- the only stone entry; its sub-chapter is excavation-oriented) | Ma_40_84 |
| `mineral_mixture` | Mixed mineral (concrete/brick/ceramic) | mineral | 17 01 07 | --- |
| `gypsum` | Gypsum (plasterboard, blocks) | mineral | 17 08 02 | --- |
| `glass` | Glass | mineral | 17 02 02 | Ma_40_35 |
| `steel` | Steel | metal | 17 04 05 | Ma_40_52_83 |
| `stainless_steel` | Stainless steel | metal | 17 04 05 | Ma_40_52_83 |
| `cast_iron` | Cast / wrought iron | metal | 17 04 05 | --- |
| `aluminium` | Aluminium | metal | 17 04 02 | --- |
| `copper` | Copper, bronze, brass | metal | 17 04 01 | --- |
| `zinc` | Zinc | metal | 17 04 04 | Ma_40_52_99 |
| `lead` | Lead | metal | 17 04 03 | Ma_40_52_47 |
| `timber` | Solid timber | bio-based | 17 02 01 | Ma_60_97 |
| `engineered_timber` | Engineered timber (glulam, CLT, LVL) | bio-based | 17 02 01 | --- |
| `wood_based_panel` | Wood-based panel (plywood, OSB, particleboard, MDF) | bio-based | 17 02 01 | --- |
| `bamboo` | Bamboo | bio-based | 17 02 01 (a grass, handled as wood) | --- |
| `straw_hemp` | Straw / hemp / other plant fibre | bio-based | 17 06 04 (as insulation; otherwise assign 17 09 04) | --- |
| `mineral_composite` | Mineral composite (acrylic solid surface) | polymer | 17 02 03 | --- |
| `acrylic` | Acrylic (PMMA) | polymer | 17 02 03 | --- |
| `polycarbonate` | Polycarbonate | polymer | 17 02 03 | Ma_60_65_12 |
| `pvc` | PVC | polymer | 17 02 03 | Ma_60_65_96 |
| `polyethylene` | Polyethylene | polymer | 17 02 03 | Ma_60_65_28 |
| `asphalt` | Asphalt | bituminous | 17 03 02 | Ma_40_19_04 |
| `bitumen_membrane` | Bituminous membrane | bituminous | 17 03 02 | --- |
| `mineral_wool` | Mineral wool insulation | insulation | 17 06 04 | --- |
| `polymer_foam` | Polymer foam insulation (EPS, XPS, PUR/PIR) | insulation | 17 06 04 | --- |
| `mixed` | Mixed / composite element | other | 17 09 04 | --- |
| `unknown` | Unknown | other | 17 09 04 | --- |

Multi-material pieces (Annex IV 1.2(e) "main materials", plural) --> `secondary_materials[]`,
**deferred** (additive, 6.8). Until then `material` is the main material.

## 3. Documents

Conventions unchanged from 0.5: `_id` = UUID string; timestamps ISO-8601 UTC strings with `Z`;
`etag` = sha256 over canonical JSON excluding `etag`/`lastmodified`; Pydantic v2 models with
`populate_by_name`; `extra = "ignore"` on envelopes, **`extra = "forbid"` on typed payloads**.

### 3.1 `component_identities`

```jsonc
{
  "_id": "uuid",                             // CPR: batch / serial number --- Art 22(5), Annex V 1(a); section 10.2
  "catalog_number": 42,                      // unchanged: monotonic, never recycled
                                             // CPR: unique identification code of the product type --- Art 22(5), Art 18(2)(d), Annex V 1(a); section 10.2
  "original_function": "IfcBeam",            // section 2.1 --- REPLACES `type`
                                             // CPR: input to product family (Annex VII) and BIM interoperability (Art 75(2)(a)); section 10.3
  "material": "concrete",                    // section 2.10 --- FK --> materials; controlled, admin-extensible
  "material_class": "17 01 01", "material_class_source": "derived" | "assigned",   // section 2.10 --- EU List of Waste ch. 17
  "trade_name": "..." | null,                  // section 2.10 --- brand / product name (e.g. "Corian")
                                             // CPR: "main materials used" --- Annex IV 1.2(e); input to product family (Annex VII)
  "dataset": "sas_cita_scans",               // FK --> datasets._id (section 3.6); no longer a free string
  "manufactured_at": "...", "manufactured_precision": "year",
  "origin": {                                // section 3.1.1 --- REPLACES salvage_source + salvaged_at (decision 6.1)
                                             // CPR: when kind == deinstallation this IS "date and place of the latest deinstallation" --- Annex V 1(h);
                                             //      year of deinstallation on the CE mark --- Art 18(2)(a); life cycle of a used product starts here --- Art 3(53);
                                             //      deinstallation *process* on request --- Art 21(3)
    "kind": "deinstallation" | "demolition" | "offcut" | "surplus" | "unknown",   // section 2.8
    "at": "..." | null, "at_precision": "day",
    "place": { "name": "...", "address": "...", "location": { "lat": ..., "lon": ... } | null } | null,
    "construction_work": { "name": "...", "identifier": "..." | null, "year_built": 1968 | null, "use": "..." | null } | null,
    "method": "..." | null,
    "performed_by": [ /* actor section 3.3.1 */ ],
    "notes": "..." | null
  },
  "parent_identities": ["uuid"] | null,      // CPR: key parts / kits lineage --- Art 3(16), 3(17), Art 76(2)(a)(vii)
  "inherited_fields": ["origin", "manufactured_at", "material", "trade_name", "original_function"],   // section 3.1.2; server-maintained, [] for roots
  "inherited_from": "uuid" | null,           // section 3.1.2; the parent the listed fields mirror
  "exit": {                                  // section 3.1.3 --- REPLACES consumed_at (decision 6.3); null = in circulation
                                             // CPR: retention --- the identity stays available after exit, 25 y / >=10 y, Art 75(2)(i); soft end-of-life only
    "kind": "split" | "merged" | "installed" | "recycled" | "disposed" | "returned" | "lost",   // section 2.9
    "at": "...", "at_precision": "day",
    "construction_work": { /* as origin */ } | null,
    "notes": "..." | null,
    "recorded_by_user_id": "uuid" | null     // server-set; null when set by the server (split/merge)
  } | null,
  "past_cycles": [ { "origin": { ... }, "exit": { ... } } ],   // section 3.1.3; append-only, server-written on re-entry
  "withdrawn": { "at": "...", "by_user_id": "uuid", "reason": "...", "duplicate_of": "uuid" | null } | null,   // section 3.1.4 --- record-level tombstone
  "reserved": "", "is_public": false,        // CPR: tiered access, public tier --- Art 75(2)(c), 76(2)(e--f), 78(f)
  "current_snapshot_id": "uuid",

  "properties": {                            // DERIVED section 4.4 --- never written by clients
                                             // CPR: declared performances per essential characteristic (value / level / class, or NULL) --- Annex V 9(a--b), Art 3(6--7), 3(13--14);
                                             //      projection rule (conservative bound) in section 10.3; environmental characteristics Annex II via `env_*` quantities
    "compressive_strength": {
      "range": [36.2, 40.1], "unit": "MPa",
      "confidence": 0.93, "source": "destructive",
      "n": 4, "evidence_ids": ["..."],
      "inherited_from": null,                 // or [parent ids] (merges: several)
      "derived_at": "..."
    }
  },
  "properties_version": 1,                   // fold-rule version that produced `properties`

  "attributes": {},                          // kept; migration empties the three ad-hoc keys (section 8)
                                             // capture metadata lives on the SNAPSHOT (section 3.2, decision 7.7) --- a re-scan has its own
  "created": "...", "lastmodified": "..."
}
```

Removed: `type`, `salvage_source`, `salvaged_at`, `consumed_at`; `material` becomes an FK.
Added: `original_function`, `material_class(+_source)`, `trade_name`, `origin`, `exit`,
`past_cycles`, `inherited_fields`, `inherited_from`, `withdrawn`, `properties`,
`properties_version`.

#### 3.1.1 `origin` --- how the piece entered circulation

One block per identity, describing its **latest** origin: the event that took it out of its
previous context (a building, a demolition, a production line, a stock) and made it available
for reuse. Authored, not derived. Replaces the 0.5 free-text `salvage_source`, which in the data
mixed an organisation, an address, a place and a stray note in one string.

| field | meaning | applies to `kind` |
|---|---|---|
| `kind` | section 2.8 --- decides which regulatory reading applies | all |
| `at` / `at_precision` | when the piece left its previous context (deinstalled, recovered from demolition, cut off, taken from stock). Precision per section 2.7; `year` is legitimate (CE mark carries the year only, CPR Art 18(2)(a)) | all |
| `place` | where that happened: `name`, postal `address`, optional `location` | all |
| `construction_work` | the **works** it left --- never the company (that is `performed_by`). CPR Art 3 sense: "buildings and civil engineering works ... including ... roads, bridges, tunnels". `name` (e.g. "Lichtwiese Campus Infrastructure --- pedestrian bridge"), `use` (e.g. "pedestrian bridge"), `year_built`; `identifier` is free-form now, intended for a digital-building-logbook or cadastral id (EPBD, section 10.6) | `deinstallation`, `demolition` only (I16) |
| `method` | free text: how it was deinstalled / recovered --- the Art 21(3) "process of deinstalling" | all; expected for `deinstallation` |
| `performed_by` | actors (section 3.3.1): deinstaller, demolition contractor, fabricator that produced the offcut, stockist | all |
| `notes` | anything that fits nowhere else | all |

`origin` is `null` only on identities created without any provenance; migration never produces
`null` (it writes `kind: unknown`). CPR export: Annex V 1(h) is filled from `origin` **iff**
`kind == "deinstallation"`; otherwise the field is emitted empty and `kind` is carried as a note
(section 10.3).

#### 3.1.2 Lineage inheritance (split / merge children)

A cut does not change a piece's past. The **inheritable fields** --- `origin`,
`manufactured_at` + `manufactured_precision` (one unit), `material`, `trade_name`,
`original_function` --- are
materialized on the child by the **server**, never copied by clients. `dataset` is not inheritable.

- **Create** with `parent_identities`: each inheritable field *absent* from the payload is copied
  from the parent; its name goes into `inherited_fields`, the parent id into `inherited_from`.
  A field present in the payload is the child's own (not listed).
- **Parent PATCH** of an inheritable field: propagates to every descendant (recursive, breadth-
  first down `parent_identities`) whose `inherited_fields` still lists it, in the same request.
- **Child PATCH** of a listed field: removes it from `inherited_fields` --- the child now owns it.
  (Re-inheriting = PATCH `inherited_fields` to add it back; server re-copies.)
- **Merge** (>1 parent): a field is inherited only if all parents hold equal values; otherwise it
  stays unset (`origin.kind: unknown`, `manufactured_precision: unknown`) and must be assigned.
  `inherited_from` is then the first parent.
- Same pattern as property inheritance (section 4.4, decision 2.4) and `shape_class_source`: flat,
  queryable fields that cannot go stale because the server owns the propagation.

#### 3.1.3 `exit` --- how the piece left circulation

The counterpart of `origin`. `exit == null` means the piece is in the catalogue's circulation
(available, reservable). Replaces 0.5 `consumed_at`, which conflated a piece that no longer
exists (split, recycled) with one that exists elsewhere (installed, returned).

- **Split / merge are server-set.** Creating an identity whose `parent_identities` includes a
  parent with `exit == null` sets that parent's `exit = {kind: split | merged, at: <child's
  first-snapshot effective_from>, recorded_by_user_id: null}` (`merged` when the child has >1
  parent). A client-set `split` without catalogued children is legal ("cut up, pieces not
  recorded").
- **Everything else is authored**: `POST /identities/{id}/exit` (`moderator(D)`, section 7.0) with the block.
  `construction_work` only for `kind == installed` (I18).
- **Re-entry** (an `installed` or `returned` piece comes back, e.g. from a temporary pavilion):
  `POST /identities/{id}/reenter` with a new `origin`. The server appends `{origin, exit}` to
  `past_cycles`, clears `exit`, writes the new `origin`. `split`, `merged`, `recycled`,
  `disposed` are terminal --- re-entry is rejected (the physical piece no longer exists as this
  identity). `past_cycles` is never client-writable.
- **Reservation** is only possible with `exit == null` (0.5 rule, unchanged).

**The moment of the cut** is the child's first snapshot's `effective_from` (valid time, section 4.1).
`manufactured_at` is never the cut date: it is when the *material* was made, inherited from the
parent. (0.5 GH wrote the child's creation timestamp into `manufactured_at` --- migration section 8
step 10b.)

#### 3.1.4 Withdrawal, redaction, purge (decision 6.4)

Retention rule (CPR Art 75(2)(i), 78(h); EN 18221): **nothing that was ever `published` is
hard-deleted.**

| record | "delete" means | effect |
|---|---|---|
| evidence, snapshot in `draft\|pending\|rejected` | hard delete (+ files) | gone; never public |
| evidence, snapshot `published` | `POST .../withdraw {reason}` --> `status: withdrawn` | out of default lists, fold, public tier, promotion (`current_snapshot_id` cannot point at it; withdrawing the current snapshot requires naming a replacement or leaves the identity without a current snapshot --> identity hidden from default lists); retrievable by id with `status` shown; files kept. `POST .../reinstate` reverses. |
| identity never published | `DELETE /identities/{id}` | hard delete, as 0.5 (reject a new v0) |
| identity ever published | `POST /identities/{id}/withdraw {reason, duplicate_of?}` | `identity.withdrawn = {at, by_user_id, reason, duplicate_of}`; hidden everywhere by default; `GET /identities/{id}` returns it with the tombstone; with `duplicate_of`, `/id/{uuid}` (section 7.5) and the component page redirect to the canonical identity (**the 0.5 hard delete was a stand-in for this**) |
| any | `?purge=1` (admin, body must repeat the id) | hard delete incl. files, then insert stub `{_id, purged_at, purged_by_user_id, reason}` in `purged_records`; every GET on that id --> **410 Gone** |
| personal data in actors | `POST /actors/redact {user_id \| name+organization}` (admin; GDPR Art 17) | in every evidence/origin/exit actor: `name`, `email`, `orcid` --> null, `redacted_at` set; `organization` kept |

```jsonc
"withdrawn": { "at": "...", "by_user_id": "uuid", "reason": "...", "duplicate_of": "uuid" | null } | null
```

### 3.2 `component_snapshots`

```jsonc
{
  "_id": "uuid", "identity_id": "uuid", "version": 2,
                                               // `virtual` REMOVED (decision 7.12): every snapshot is a state that existed
  "status": "draft" | "pending" | "published" | "rejected" | "withdrawn",   // REPLACES validated; same lifecycle as evidence (section 3.3.3, I15)
                                             // CPR: `published` = the tier visible to all actors (Art 76(2)(e)); never hard-deleted (Art 75(2)(i)) --- section 10.4
  "status_changed_by_user_id": "uuid" | null, "status_changed_at": "..." | null,
  "supersedes": "uuid" | null, "superseded_by": "uuid" | null,   // NEW section 3.2.2 --- corrections, same semantics as evidence section 3.3.4
  "name": "...",

  "effective_from": "2026-02-01T00:00:00Z",   // NEW section 4.1; always set
  "effective_from_precision": "day",

  "shape_class": "linear",                    // NEW section 4.2
  "shape_class_source": "derived" | "assigned",

  "geometry": {                              // CPR: this block is a "3D-dataset" --- Art 3(11): "shape of an object by its outer dimensions and its cavities"
    "meshes": [ { "vertices": [...], "faces": [...], "colors": [...] } ],      // unchanged
    "point_clouds": [ { "points": [...], "colors": [...] } ],                  // unchanged
    "proxies": [ /* section 3.2.1 */ ]                                                // NEW --- replaces extrusions[]; CPR: primary proxy params = "nominal dimensions" Annex V 1(d); BIM export Art 75(2)(a)
                                               // marker_points --> capture.markers (7.7); reinforcements --> evidence `reinforcement_layout` (7.8)
  },

  "capture": {                                 // NEW section 3.2.3 (decision 7.7) --- how THIS geometry was captured; replaces identity.capture
                                               // CPR: provenance of the "3D-dataset" (Art 3(11)); part of the technical documentation, Art 22(3)
    "method": "photogrammetry" | "lidar" | "structured_light" | "manual" | null,
    "device": "..." | null, "software": "..." | null, "captured_at": "..." | null, "notes": "..." | null,
    "coordinate_system": { "name": "DDU robot gripper marker plane", "description": "..." } | null,   // what the stored coordinates are relative to
    "markers": [ { "label": "blue_1", "role": "rig" | "component", "point": [x,y,z] } ],
    "fixtures": [ { "label": "end_effector", "file": "capture/<snapshot_id>/fixtures/0.ply" } ]
  } | null,

  "descriptors": { "boxscore": ..., "radial_distance_32": ..., "hks": ... },        // DERIVED, runner stage 4 (section 4.3); frame-aligned
  "properties": {                              // DERIVED section 4.4 as-of fold --- snapshot-scoped quantities only
    "spalling": { "range": [1, 2], "confidence": 0.3, "source": "visual", "n": 2, "evidence_ids": ["..."], "derived_at": "..." }
  },
  "properties_version": 1,
  "frame": { "o": [x,y,z], "x": [...], "y": [...], "z": [...] },   // DERIVED stage 1 (decision 7.10): minimum-volume box, axis convention section 4.3; REPLACES pca_frame + bbx_origin
  "bbx": [X, Y, Z],                            // DERIVED: box extents along frame x / y / z (not sorted by PCA variance)
                                               // `iframe` REMOVED (7.11): only designs gave it meaning
  "complexity": 2, "complexity_source": "derived" | "assigned",   // 0--3 ordinal, DERIVED + overridable (6.15)
  "fragment": false,                         // `assembly` REMOVED (never true; = shape_class composite) --- 6.13
                                               // `condition` REMOVED --- visual state is evidence (section 2.6, section 8 step 6b)
  "color": [r,g,b], "location": {"lat":...,"lon":...},
  "notes": "...", "quantity": 1,               // CPR: quantity > 1 is the one case where a batch shares a product type --- Art 22(5), Annex V 1(a)
  "added_by_user_id": "...", "added_by_username": "...",
  "photo_count": 0,
  "mesh_ply_resolutions": { "0": ["reduced", "detailed"] },
  "etag": "...", "created": "...", "lastmodified": "..."   // CPR: etag = integrity hash --- Art 78(h)
}
```

Removed: `geometry.extrusions`, `validated`, `condition`, `processes`, `assembly` (6.13),
`virtual` (7.12), `iframe` (7.11), `pca_frame` + `bbx_origin` (--> `frame`, 7.10),
`geometry.marker_points` (7.7), `geometry.reinforcements` (7.8). Added: `status(+_changed_*)`,
`supersedes` / `superseded_by`, `effective_from(+_precision)`, `shape_class(+_source)`,
`complexity_source`, `frame`, `geometry.proxies`, `capture` (7.7). `bbx` keeps its name with a new
meaning (extents along `frame` x / y / z).

Snapshot status semantics: `published` is what `validated: true` meant --- listable by default,
eligible for promotion to `current_snapshot_id`, on the timeline. Promotion remains a separate
act (`current_snapshot_id`), so a published snapshot need not be current. The 0.5 rule "one
pending snapshot per identity" becomes **one snapshot with `status in {draft, pending}` per
identity**. Snapshots carry no `verification` block --- geometry is a capture, not a claim.

The representation invariant becomes (section 5):

> at least one of `meshes`, `point_clouds`, or a proxy with `fit.method == "authored"`.

#### 3.2.1 Proxy entry

```jsonc
{
  "primitive": "prism",                        // section 2.3
  "role": "primary" | "part",                  // exactly one primary per snapshot
  "params": { /* Appendix B */ },
  "placement": { "o":[...], "x":[...], "y":[...], "z":[...] },   // the primitive's local axes, in stored coordinates (App. B)
  "fit": {
    "method": "authored" | "obb" | "ransac" | "lsq" | "hull",
    "source": { "kind": "meshes" | "point_clouds", "index": 0, "resolution": "detailed" | "reduced" | "inline" } | null,
    "n_points": 184220,
    "inlier_ratio": 0.94,                      // ransac only
    "rms_mm": 2.1, "max_mm": 14.7, "p95_mm": 6.3,
    "spec_version": 1, "computed_at": "..."
  },
  "deviation_maps": {                          // null when not computed
    "resolution_mm": 5.0,
    "channels": ["distance", "normal_deviation", "occupancy"],
    "faces": {
      "+z": { "file": "proxies/<snapshot_id>/0/+z.png", "width": 400, "height": 60,
              "distance": { "scale_mm": 0.01, "offset_mm": -20.0 } }
    }
  },
  "regions": [                                 // local resolution relevance; schema slot only this release
    { "label": "east connection",
      "bounds": { "min": [x,y,z], "max": [x,y,z] },   // proxy-local AABB
      "resolution_hint": "full" | "reduced" | "proxy",
      "reason": "connection" | "damage" | "feature" | "other",
      "source": "assigned" | "derived" }
  ]
}
```

`fit.method == "authored"` => `fit.source == null`, no residuals, no deviation maps. `regions`
defaults to `[]`; nothing consumes it yet (section 6).

#### 3.2.2 Freeze, corrections, state changes (decision 6.6)

Generalises ADR-015 ("geometry changes drive a new version") and closes its loopholes (file
routes on published snapshots, client-writable `descriptors`, publish-before-upload).

| class | fields | before publish | after publish |
|---|---|---|---|
| **frozen** --- claims about the piece's state | inline `geometry.*` (meshes, point_clouds, authored proxies); mesh + point-cloud PLY files; `capture` except `capture.notes` (incl. fixture files); `fragment`, `quantity`; `shape_class` / `complexity` when `assigned` | author / `moderator(D)` | never in place --> correction (below) |
| **derived** --- server only | `descriptors`, fitted proxies + `deviation_maps`, `shape_class` / `complexity` when `derived`, `properties`, `frame`, `bbx`, previews, `mesh_ply_resolutions` | server | server, any time (crons, recompute routes). **Never accepted from a client** --- `descriptors` leaves `UpdateComponentSnapshotModel` |
| **mutable metadata** | `name`, `notes`, `location`, `color` | author / `moderator(D)` | `moderator(D)` in place |
| **photos** | `photos/<sid>/*` | author / `moderator(D)` | append: `contributor(D)`; delete: `moderator(D)` |
| **valid time** | `effective_from(+precision)` | --- | `moderator(D)` (a correction of *when*, not *what*; triggers snapshot-fold recompute, section 4.4) |

Two distinct acts, both explicit:

- **State change** (cut, weathered, repaired): a **new version** with a later `effective_from`.
- **Correction** (wrong scan, wrong flag): `POST /snapshots/{sid}/supersede` with the corrected
  snapshot --> new document, next `version` number, **inherits the old `effective_from`**,
  `supersedes: <sid>`; the server sets `superseded_by` on the old one when the new one is
  published. A superseded snapshot drops out of resolution (section 4.1), the fold and default lists,
  stays retrievable, and shows as "corrected" on the timeline. If the old one was
  `current_snapshot_id`, the new one replaces it on publish.

**Creation is always `draft`.** Files (PLYs, photos) are uploaded while `draft`; then `submit`, or
for a moderator `submit` + `publish?promote=1` in one call. The 0.5 immediate-promote branch of
`create_snapshot` is removed.

#### 3.2.3 Capture (decision 7.7)

`capture` says how *this* snapshot's geometry was recorded --- and keeps everything that appears in
the capture but is **not the component** out of `geometry`:

- `coordinate_system` --- what the stored coordinates are relative to, named (e.g. the robot
  gripper's marker plane, which is what the robot needs). `null` = plain Rhino Z-up world
  coordinates of an authored or hand-oriented model. Not to be confused with the snapshot's
  derived `frame`, the canonical orientation (section 4.3).
- `markers` --- labelled reference points: `role: rig` (fixed on the capture rig, e.g. the four
  blue markers of the DDU gripper) or `role: component` (stuck on the piece, e.g. green markers).
- `fixtures` --- meshes captured together with the piece that are not part of it (the gripper that
  held a stone during scanning), one PLY each under `capture/<snapshot_id>/fixtures/`.

No derivation (section 4.3) ever reads markers or fixtures, and they never satisfy I1. The 0.5
convention "`meshes[0]` is the piece, anything else is whatever" (descriptors read only index 0)
ends: every entry of `geometry.meshes` / `point_clouds` is the component.

### 3.3 `component_evidence`

Replaces `component_measurements` (unused binding at `main_fastapi.py:90`).

```jsonc
{
  "_id": "uuid",
  "identity_id": "uuid",                       // required, immutable
                                               // no campaign_id (decision 7.2): the dataset is the study, the record's own fields the occasion

  "method": "core_compression",                // section 2.5 discriminator
  "method_version": 1,
  "source_tier": "destructive",                // copied from method spec at write; indexable
  "standard": { "code": "EN 12504-1", "year": 2019 } | null,   // CPR: technical reference documents --- Annex V 8; assessment methods incl. used products --- Art 31(1)

  "observed_at": "2026-02-27T14:30:00Z",       // when the RESULT was produced (SOSA resultTime)
  "observed_at_precision": "exact",
  "sampled_at": "2026-02-20T11:00:00Z" | null, // when the COMPONENT was sampled (phenomenonTime)
  "sampled_at_precision": "exact" | null,

  "performed_by": [ /* section 3.3.1 */ ],          // CPR: notified body / TAB / laboratory identification --- Annex V 5--7; section 10.3
  "recorded_by_user_id": "uuid", "recorded_by_username": "...",   // server-set

  "position": {                                // section 3.3.2; may be {"kind":"none", "description": "..."}
    "kind": "point" | "region" | "face" | "none",
    "snapshot_id": "uuid" | null,              // whose stored coordinates `point` is in (authored, section 3.3.2)
    "point": [x,y,z] | null,
    "description": "north face, mid-span"
  },

  "summary": {                                 // exactly one; the fold input
                                               // CPR: one performance per essential characteristic, "levels or classes" --- Art 3(13--15), Annex V 9(b)
    "quantity": "compressive_strength",
    "value": 38.3, "range": null,              // value for measurements; range for claims; either or both
    "unit": "MPa", "unit_entered": "N/mm2",
    "kind": "measured" | "claimed",
    "uncertainty": { "type": "stddev" | "expanded" | "range" | "none", "value": 1.2, "k": 2 } | null
  },
  "derived": [                                 // zero or more; never feed the fold unless quantity differs
    { "quantity": "compressive_strength_in_situ", "value": 38.3, "unit": "MPa",
      "kind": "derived", "model": { "kind": "en_13791", "reference": "...", "note": "..." } }
  ],

  "payload": { /* Appendix A, discriminated on method */ },

  "destructive": true,                         // copied from method spec
  "attachments": [                             // decision 7.3 --- replaces attachment_count; files at evidence/<_id>/<index>.<ext> (section 3.5)
                                               // CPR: certificates / validation reports attached --- Annex V 7; documents exempt from machine-readability, Art 77(1)(d); integrity per file, Art 78(h)
    { "index": 0, "name": "Pruefbericht_2026-117.pdf", "media_type": "application/pdf", "size": 812345,
      "sha256": "...",                           // same checksum on several records = the same document (e.g. one lab report for 8 cores)
      "uploaded_by_user_id": "uuid", "uploaded_at": "...",
      "removed": { "at": "...", "by_user_id": "uuid", "reason": "..." } | null }   // tombstone: file deleted, entry kept
  ],
  "notes": "...",

  "status": "draft" | "pending" | "published" | "rejected" | "withdrawn",   // moderation lifecycle (section 3.3.3, I15)
  "status_changed_by_user_id": "uuid" | null, "status_changed_at": "..." | null,
  "verification": {                                            // epistemic state (section 3.3.3)
                                                               // CPR: `accredited` <=> notified body (Art 52 id) or accreditation (Art 3(51)); Annex V 5, 7
    "state": "unverified" | "self_attested" | "reviewed" | "accredited",
    "by": { /* actor */ } | null, "at": "..." | null, "note": "..." | null
  },

  "supersedes": "uuid" | null,                 // corrections: section 3.3.4
  "superseded_by": "uuid" | null,              // CPR: reliability + integrity, Art 78(h); versioned declarations, Annex V note (3)

  "etag": "...", "created": "...", "lastmodified": "..."
}
```

#### 3.3.1 Actor

```jsonc
{ "kind": "user" | "person" | "organization",
  "user_id": "uuid" | null,
  "name": "...", "organization": "...", "organization_ror": "https://ror.org/..." | null,
  "orcid": "..." | null, "email": "..." | null,
  "role": "operator" | "supervisor" | "laboratory" | "client" | "witness",
  "accreditation": {                                   // decision 6.8; null unless the organization is accredited
    "scheme": "iso_17025" | "notified_body",           // lab accreditation (e.g. DAkkS) | CPR notified body (Art 52 number)
    "id": "D-PL-12345-01-00" | "NB 1234",
    "body": "DAkkS" | "...",                             // accrediting / notifying authority
    "scope": ["EN 12504-1", "EN 12390-3"],             // standards covered
    "valid_until": "..." | null
  } | null,
  "redacted_at": "..." | null }                          // GDPR redaction, section 3.1.4
// CPR: no end-user personal data without consent --- Art 77(1)(e) (GDPR Art 6); Annex V 5--7 notified bodies / reports
```

`verification.state == "accredited"` requires at least one `performed_by` actor whose
`accreditation.scope` contains the evidence's `standard.code` and whose `valid_until` is null or
>= `observed_at` (I22). Lab accreditation (ISO/IEC 17025) is the normal case for a core test;
notified bodies (CPR Art 52) are for conformity assessment --- both are needed.

Projections (decision 6.13): anonymous --> `organization` only; authenticated users --> + `name`,
`orcid`, `role`; `email` only for `admin` and `moderator(D)` of the record's dataset, **never** in
list responses (GDPR data minimisation).

#### 3.3.2 Position

`position.snapshot_id` is **authored** (the snapshot the operator picked the point on), unlike the
derived snapshot context. `point` is in that snapshot's stored geometry coordinates (Rhino Z-up;
for a robot scan, the coordinate system named by `capture.coordinate_system`, section 3.2.3) --- never in
the canonical `frame`. `kind: "none"` + `description` must always be sufficient.

#### 3.3.3 Moderation vs. verification

The 0.5 snapshot `validated` boolean was a **publish gate** (admin-only, "pending approval",
default filter everywhere). One bit conflates three concerns, so they are split --- and the same
`status` lifecycle now applies to snapshots (section 3.2):

| field | concern | actor | effect |
|---|---|---|---|
| `status` | moderation --- is this allowed in the catalog? | admin / moderator | `published` is the only status that lists by default, is visible anonymously, and enters the fold |
| `verification.state` | epistemic --- has someone competent confirmed it is what it claims? | reviewer, or the responsible organization attesting its own result | scales confidence in the fold (section 4.4) |
| freeze | immutability | system, on `status --> published` | result-bearing fields become read-only; corrections supersede (section 3.3.4) |

Lifecycle: `draft` (author only, editable) --> `pending` (submitted) --> `published` \| `rejected`;
`published` --> `withdrawn` (tombstone, section 3.1.4) and back by reinstatement; a published evidence
record also leaves the default set when superseded (section 3.3.4).
`verification` is independent: it can be set before or after publishing, by anyone with the
`reviewer` role of the record's dataset (decision 6.5: per-dataset membership role, orthogonal
to `moderator`). Verification factors are policy constants:

| `verification.state` | factor |
|---|---|
| `unverified` | 0.70 |
| `self_attested` | 0.85 |
| `reviewed` | 1.00 |
| `accredited` | 1.00 (the responsible organization holds accreditation for the method; recorded on the actor) |

Snapshots use the same `status` enum and transitions (I15) but have no `verification`.

#### 3.3.4 Corrections --- supersede, don't edit

Once `status == "published"`, these fields are frozen: `payload`, `summary`, `derived`,
`observed_at*`, `sampled_at*`, `performed_by`, `standard`, `method*`, `position.snapshot_id`,
`position.point`. A correction is a **new record** with `supersedes: <old_id>`; the server sets
`superseded_by` on the old one, which drops out of default listings and the fold but stays
retrievable by id and appears in the timeline as "superseded". Still editable in place after
publish: `notes`, `position.description`, `verification`. **Attachments are add-only after
publish** (decision 7.3): `contributor(D)` adds; only `moderator(D)` removes, with a reason, and
the `attachments[]` entry stays as a tombstone (`removed`) while the file is deleted --- the same
rule as snapshot photos (section 3.2.2).

Every list query defaults to `superseded_by: null`; `?include=superseded` lifts it.

### 3.4 `designs` --- removed (decision 7.11)

CSC records pieces, not designs. Evaluating a design built from catalog components happens in GH
on fetched passports; published, editable designs belong in tools built for that (e.g. Speckle).
The `designs` collection, its routes, the web `/designs` pages and the GH design components go.

### 3.5 On-disk companions

```
meshes/<snapshot_id>/<i>/{reduced,detailed}.ply     unchanged
point_clouds/<snapshot_id>/<i>.ply                  unchanged
previews/<snapshot_id>.webp                         unchanged
photos/<snapshot_id>/<index>.jpg                    unchanged
proxies/<snapshot_id>/<i>/<face_id>.png             NEW  16-bit PNG, one per face, channels per section 3.2.1
capture/<snapshot_id>/fixtures/<i>.ply              NEW  fixture meshes (e.g. robot gripper), never read by derivations (section 3.2.3)
evidence/<evidence_id>/<index>.<ext>                NEW  pdf | jpg | png | webp; sniffed, not trusted  (CPR: Annex V 7 reports; retention Art 75(2)(i))
```

Evidence attachments (decision 7.3): one upload attached to several records is stored once **per
record** --- hard links where the filesystem allows, else copies --- so every record owns its files
and no reference counting exists. PDFs are stored byte-for-byte; images go through the snapshot
photo pipeline (`snapshot_images.py`). `sha256` in `attachments[]` is computed over the stored
bytes.

**Photo metadata (decision 7.13)** --- for snapshot photos and evidence images alike, the upload
pipeline removes the EXIF GPS block, owner / artist and body serial number, and keeps orientation,
capture time (`DateTimeOriginal`) and camera make / model. Where a piece is stays the snapshot's
chosen `location`, never the photo's GPS.

New env vars: `SNAPSHOT_PROXIES_DIR`, `SNAPSHOT_CAPTURE_DIR`, `EVIDENCE_ATTACHMENTS_DIR`
(+ upload limit), added to `_REQUIRED_ENV`.

---

### 3.6 `datasets` (NEW collection --- decision 6.5)

A dataset is a **project**: the unit of membership, permission and visibility. Every identity
belongs to exactly one.

```jsonc
{
  "_id": "sas_cita_scans",                   // slug, immutable; = identity.dataset (FK)
  "name": "SAS CITA scans", "description": "...",
  "visibility": "members" | "catalog",       // DEFAULT "members" (user decision)
  "members": [
    { "user_id": "uuid", "roles": ["contributor", "reviewer", "moderator"],   // a set, not a ladder
      "added_by_user_id": "uuid", "added_at": "..." }
  ],
  "created": "...", "lastmodified": "..."
}
```

Index: `members.user_id`. `identity.dataset` stops being a merge-vocab string (section 2 extension
policy: the merge pattern is removed; `datasets` and `materials` are collections).

**Visibility of published components** --- three tiers:

| viewer | sees a published component of dataset D when ... |
|---|---|
| anonymous | the component is `is_public` ("completely public") |
| logged in, not a member of D | D is `catalog`, **or** the component is `is_public` |
| member of D | always --- all of D, plus the row above for every other dataset |
| admin | always |

As one predicate: `admin or member(D) or (logged_in and D.visibility == catalog) or is_public`.
Unpublished records: section 7.0.

### 3.7 `users` changes

Global `role in {user, admin}` unchanged. `admin` = system role and **implicit full membership of
every dataset** --- kept as the testing and emergency hatch (user decision); at least one enabled
admin must exist (I20). No `moderated_datasets` field (0.5.0.2 plan superseded by memberships).
The shared `ddu` account is retired (section 8 step 11).

## 4. Derivations

All are pure functions in `apps/catalog/`, unit-tested without a database, invoked from routes
and from crons. Each has a `*_VERSION` constant stored alongside its output so a rule change can
be detected and recomputed (`--recompute`).

### 4.1 Snapshot timeline --- `timeline.py`

`effective_from` is **valid time**: when the physical state this snapshot describes began.
(CPR: the DPP must be kept "accurate, complete, and up-to-date" with arrangements for updating an
existing product's passport, Art 76(1), 75(2)(e) --- the snapshot chain *is* that arrangement.)

- Set when the snapshot is created: now, or the author's value for a state that began earlier
  (the snapshot form, section 7.6). A correction inherits its predecessor's (section 3.2.2).
- After publish, `moderator(D)`-editable via `PATCH /snapshots/{sid}` (section 7.1) --- decision 6.6.
- Always set: there are no virtual snapshots (decision 7.12).
- Monotonic in `version` per identity over non-superseded, non-withdrawn snapshots (I3); a
  correction shares its predecessor's value. Violations are rejected.

```
resolve_snapshot_at(snapshots, at) -> Context
  candidates = [s for s in snapshots if s.status == "published"
                and s.superseded_by is None and s.effective_from <= at]
  if none:            Context(snapshot_id=None, resolution="before_first")
  else:               s = max(candidates, key=(effective_from, version))
                      resolution = "exact" | "approximate" (if effective_from_precision coarser than `at` gap)
  if identity.exit and at > identity.exit.at:     resolution="after_exit"
```

**Never persisted** on the evidence document. Returned under `context` when
`?include=context`. For `core_compression`, `at = sampled_at`; for all other methods
`at = observed_at`. (Rule: method spec declares `context_time: "sampled_at" | "observed_at"`.)

### 4.2 Shape class --- `shape_class.py`

Inputs: the frame's box extents (`bbx`, section 4.3 stage 1) sorted `e1 >= e2 >= e3` and
`descriptors.{boxscore, spherescore, linescore, planescore}` once they exist. Sorting makes the
class independent of the frame's axis order, so the column rule of stage 1 (which reads the
class) cannot loop: stage 1 runs with the current class (none on a new snapshot --> the default
lying convention), stage 2 derives the class, and stage 1 re-runs only if the class became
`linear` on an `IfcColumn`.

```
if boxscore > T_IRREGULAR:                  irregular       # hull << OBB: pocketed, blobby
elif e1/e2 >= T_LINEAR:                     linear
elif e2/e3 >= T_PLANAR:                     planar
else:                                       block
```

Initial thresholds `T_LINEAR = 4`, `T_PLANAR = 4`, `T_IRREGULAR = 25` --- **to be tuned against
the 701 snapshots of dump 260916 before freezing**; the tuning script and its confusion table are part of the
deliverable. `composite` is never produced. Stored with `shape_class_source: "derived"`; a user
override writes `"assigned"` and is not overwritten by recompute.

### 4.2b Complexity --- `complexity.py` (decision 6.15)

Ordinal 0--3 (0 simple, 1 normal, 2 complex, 3 very complex). Inputs: primary-proxy residual
`p95_mm / e1` (how far the piece departs from its proxy), `boxscore` (hull concavity), and
`shape_class == composite` => >= 2. Thresholds tuned by the same script as section 4.2 against the
**71 `sas_cita_scans` ratings, which are authored per element** (user) --- the only genuine labels;
confusion table part of the deliverable. `complexity_source: derived | assigned`; assigned is never
overwritten.

### 4.3 Proxy fitting --- `proxies/registry.py` + `proxies/specs.py`

Mirrors `descriptors/registry.py`. One `ProxySpec` per primitive:

```
ProxySpec(name, params_model, fit, faces, uv_map, deviation, applicable_shape_classes)
```

Default primary proxy by `shape_class` (section 6).

**Derivation is server-side only (decision 6.14).** Clients upload the source geometry they have ---
meshes, point clouds, or an authored primitive (e.g. a GH extrusion --> authored prism proxy) --- and
nothing derived. `/utility/compute-snapshot-orientation` and client-sent `bbx` / `bbx_origin` /
`pca_frame` / `frame` / `iframe` / `descriptors` are removed; the GH bridge stops computing frames.

**One runner, ordered stages** --- `main_geometry.py --stages frame,shape_class,proxies,descriptors,complexity,previews
[--recompute] [--limit] [--dry-run] [--snapshot <sid>]`, replacing `main_descriptors_simple.py` and
`main_previewgen.py` as separate crons. Order is fixed because each stage reads the previous one:

| # | stage | reads | writes | cost | when |
|---|---|---|---|---|---|
| 1 | `frame` | source geometry, `shape_class`, identity `original_function` | `frame`, `bbx` (no proxy --- decision 7.10) | cheap | **synchronous** on every source-geometry write to a draft (create, PLY upload/replace) and on submit; again when `original_function` or `shape_class` changes |
| 2 | `shape_class` | stage 1 extents + scores (if present) | `shape_class` (unless `assigned`) | cheap | synchronous, right after 1 (re-run after 4 once scores exist) |
| 3 | `proxies` | source + `shape_class` | fitted primary/part proxies, residuals, `deviation_maps` | expensive | async runner |
| 4 | `descriptors` | source + `frame` (radial section, rest alignment) | `descriptors` | expensive | async runner |
| 5 | `complexity` | proxy residuals (`p95_mm` / size), `boxscore`, part count | `complexity` 0--3 (unless `assigned`) | cheap | async, after 3--4 |
| 6 | `previews` | source / proxies | `previews/<sid>.webp` | medium | async runner |

Each stage is idempotent and skips snapshots whose stored `*_VERSION` equals the code's; the cron
sweeps everything stale. Authored proxies are never refitted but still feed stage 1--2 (frame
from the authored primitive).

**The frame (stage 1, decision 7.10)** is the piece's standard orientation and size, used by GH
(`ApplyFrame`, filters, arrangement), the web filters and columns, the component map, the
descriptors and the shape class. It is **not a proxy**:

1. Minimum-volume oriented bounding box of all component geometry (meshes, clouds, authored
   primitives' surfaces; never `capture` markers / fixtures) --- `trimesh.bounds.oriented_bounds`.
   Edge-aligned for box-like pieces; vertex PCA is not used (it lands on diagonals when two
   extents are similar or vertex density is uneven).
2. Axes by extent: **longest --> x, middle --> y, shortest --> z** (lying on its largest face);
   **`shape_class == linear` and `original_function == IfcColumn`: longest --> z, middle --> x,
   shortest --> y** (standing). Same rule as the add-component wizard's `canonicalizeBoxAxesMm`.
3. Right-handed; signs deterministic (fixed rule on the geometry, so a re-run gives the same
   frame); `frame.o` = box centre; `bbx` = extents along x / y / z.

Recomputed when `original_function` or `shape_class` changes.

**The frame is a transform, never a re-orientation** (user; the reason 0.5 introduced
`pca_frame`). Stored geometry keeps the coordinates it was uploaded in, whatever produced them ---
the DDU rubble scans stay in the robot gripper's marker plane (`capture.coordinate_system`),
which the robot workflow needs. `frame` maps those stored coordinates to the canonical
orientation, so the canonical orientation is always retrievable (GH `ApplyFrame`, the viewer's
"canonical" view) and the upload orientation is never lost or overwritten. Nothing forces an
orientation on upload.
"As installed" orientation (beam depth vertical, top face up) is not derivable from geometry --- a
later assigned override (additive).

Proxy fitting per snapshot (stage 3):

1. Load highest-resolution source (`detailed.ply` > `reduced.ply` > inline mesh > cloud PLY >
   inline cloud), same priority as descriptors --- over **all** component meshes / clouds, never
   `capture` markers or fixtures (section 3.2.3).
2. Fit per spec --- **no new dependency** (decision 6.11; numpy, scipy, trimesh, shapely only):
   - `box`: `obb` = the frame's box (stage 1), optional `lsq` refine.
   - `prism`, planar shape class: the frame's shortest axis = thickness direction; project
     points; outline via `shapely.concave_hull` (already used by the radial signature) x thickness.
   - `prism`, linear shape class: `trimesh` section at mid-span across the frame's longest axis -->
     profile polygon (shapely) x length.
   - `cylinder`: the frame's longest axis; algebraic circle fit (Kasa/Taubin) on the projected section
     inside an **in-house RANSAC loop** (`proxies/robust.py`, ~50 lines numpy, seeded RNG for
     reproducibility) --> `fit.method: ransac`, `inlier_ratio`.
   - `hull`: `trimesh` convex hull, deterministic.
   Rejected: Open3D (heavy wheel + system GL libs on shared hosting, two functions used),
   `pyransac3d` (unmaintained).
3. Residuals: signed distance of every source point to the proxy surface --> `rms/p95/max`,
   `inlier_ratio` at a tolerance from the spec.
4. Deviation maps: transform points into the proxy's placement; for each face, orthographic
   projection onto the face plane, regular grid at `resolution_mm`; per cell aggregate mean signed
   distance, mean angle between point normal and face normal, and occupancy count --> three 16-bit
   channels. Cylinder lateral face unrolls to (theta, z). Hull faces are triangles, one map each is
   too many --- **hull uses a single spherical (theta, phi) map** of concavity depth instead.
5. Write `fit` and `deviation_maps`. The frame (`frame`, `bbx`) is stage 1's and is never
   rewritten from a proxy.

Authored proxies (`fit.method == "authored"`) are skipped by the cron.

**HKS descriptor (stage 4, decision 8.6).** The heat kernel signature is computed on **3000 points
spread evenly over the component's surface** with `robust_laplacian.point_cloud_laplacian`, never
on the mesh topology and never on the convex hull:

1. Sample: meshes and authored primitives area-uniformly; point clouds thinned to the same size;
   fixed seed; all component geometry, never `capture` markers / fixtures (I23).
2. 64 non-zero eigenpairs of `L phi = lambda M phi`; time grid **fixed in area-normalised units**
   (one grid for the catalogue, not per shape), so values compare across pieces.
3. Per-point HKS, mass-weighted mean + variance pooling, L2-normalised (as in `hks_features.py`).

Intrinsic, so it needs no frame (8.1). Why points: in the 260916 probe every mesh failure came from
a mesh in disconnected pieces (scan islands; unmerged seams) --- the sample never failed (169 / 169)
and ranks pieces like the intact mesh (rho 0.98); the hull always works but describes the envelope
only (rho 0.34). Errors raise and are recorded by the runner; `HKS_VERSION` versions the result.

### 4.4 Property fold --- `properties.py`

One pure function, two call sites that differ only in the input filter and the target:

| target | input set | runs on |
|---|---|---|
| `identity.properties` | all published, non-superseded evidence for the identity; quantities with `scope == identity` | evidence publish / withdraw / reinstate / supersede / verification change; identity creation with parents (inheritance); **a parent's `properties` changing** (recomputes every descendant that still inherits --- same propagation as section 3.1.2) |
| `snapshot.properties` (per snapshot) | the **as-of** set: published, non-superseded evidence whose resolved context (section 4.1) is *this* snapshot; quantities with `scope == snapshot` | the same evidence events, **plus** any `effective_from` change on any snapshot of the identity (it moves the windows), plus snapshot publish / withdraw / reinstate / supersede |

Unpublished evidence (draft, pending, rejected) never enters the fold, so creating, rejecting or
hard-deleting it triggers nothing.

Both also under a `--recompute` cron. Inheritance (parents) applies to the identity target only.

```
fold(quantities, evidence, parents_of=None) -> properties
  E = evidence with status == "published" and superseded_by == null      # caller pre-filters by as-of
  R = [(e, r) for e in E for r in [e.summary, *e.derived]]               # every result a record carries (I7: one per quantity per record)
  for quantity q in quantities:                                           # caller passes the target's scope
    Rq = [(e, r) for (e, r) in R if r.quantity == q]
    if Rq:
      top = first tier in ranking[q] with any e.source_tier == tier for (e, r) in Rq   # highest tier wins outright
      Rt = [(e, r) in Rq if e.source_tier == top]
      lo = min(r.range[0] if r.range else r.value - u(r)), hi = max(r.range[1] if r.range else r.value + u(r))
      n = len(Rt)                                                         # records, one result each
      v = mean(VERIFICATION_FACTOR[e.verification.state] for (e, r) in Rt)   # section 3.3.3
      confidence = min(0.99, (1 - (1 - base[top]) * n ** -ALPHA) * v)   # ALPHA = 0.5
      properties[q] = {range:[lo,hi], unit, confidence, source: top, n, evidence_ids, inherited_from: null}
    elif parents_of and (parents := parents_of()):                        # identity target only
      P = [p for p in parents if p.properties[q]]
      if P:                                                               # merge (>1): union, weakest confidence (6.13)
        properties[q] = {range: union(p.properties[q].range for p in P), unit,
                         confidence: min(p.properties[q].confidence for p in P) * INHERIT_K,
                         source: "inherited", inherited_from: [p._id for p in P], n: 0}
```

`u(r)` = the result's expanded uncertainty if present, else 0 (`derived[]` entries carry none).
A `derived[]` result enters with its record's `source_tier` --- a strength estimated from a rebound
set (ndt) is outranked by one converted from a core (destructive). Categorical quantities: `range`
is the set of distinct values in the top tier; confidence as above. Ordinal: min..max.

Lower-tier evidence is not folded but is returned by `GET /identities/{id}/properties` under
`outranked_evidence_ids` so the UI can show "archival claim outranked by core test" --- distinct from
*superseded* (a correction, section 3.3.4).

### 4.5 Evidence method registry --- `evidence/registry.py` + `evidence/specs.py`

```
EvidenceMethodSpec(
  name, payload_model, source_tier, destructive, default_standard,
  summary_quantity, summary_unit, context_time,
  derive_summary(payload) -> summary,           # median; F/A
  validate(payload, standard) -> list[str],     # n>=9; F/A tolerance; l/d class
)
```

`ALL_EVIDENCE_SPECS` drives the discriminated union, JSON Schema endpoints, `GET
/evidence/methods`, and the frontend form registry. **Adding a method = adding one spec.**

`source_tier` is a constant for every method except `reinforcement_layout`, where it is a function
of the payload (`basis`: `drawing` --> `archival`, `scan` --> `ndt`, `exposed` --> `visual`; decision
7.8). The record's `source_tier` is still copied at write time and indexable.

---

## 5. Invariants (backend must reject)

IDs are stable (referenced throughout); I12 is kept as a tombstone.

| # | Rule |
|---|---|
| I1 | Snapshot geometry has >=1 of `meshes`, `point_clouds`, or a proxy with `fit.method == "authored"`. |
| I2 | Exactly one proxy with `role == "primary"` per snapshot once proxies exist. |
| I3 | `effective_from` is always set; over non-superseded, non-withdrawn snapshots it is monotonic in `version` per identity (a superseding snapshot shares its predecessor's `effective_from`). |
| I3b | At most one snapshot with `status in {draft, pending}` per identity. `current_snapshot_id` must reference a `published` snapshot. |
| I4 | `shape_class == "composite"` => `shape_class_source == "assigned"`. |
| I5 | Evidence `identity_id` is immutable after create. |
| I6 | `summary` has `value` or `range` (or both), matching the quantity's kind and canonical unit after conversion. |
| I7 | Within one record, `summary.quantity` and every `derived[].quantity` are pairwise distinct --- a derived value never shadows the measured one, and each quantity has at most one result per record (the fold counts records, section 4.4). |
| I8 | `payload` validates against the method's model with `extra = "forbid"`, plus `spec.validate()` returns no errors. |
| I9 | `position.snapshot_id`, if set, belongs to the same `identity_id`. |
| I10 | `observed_at >= sampled_at` when both present. |
| I11 | `properties` is never accepted from a client; any write path recomputes it. |
| I12 | *dropped (6.13)* --- function and shape are orthogonal (4.1). |
| I13 | Frozen fields (section 3.3.4) of a `published` evidence record cannot be changed by PATCH; the only path is a superseding record. |
| I14 | `supersedes` must reference a `published` record of the same `identity_id` and same `method`; a record can be superseded at most once (no forks). |
| I15 | `status` transitions (snapshots and evidence): `draft-->pending`, `pending-->published\|rejected`, `rejected-->draft` (resubmit), `published-->withdrawn` (`moderator(D)`, reason required), `withdrawn-->published` (`moderator(D)` reinstate). Hard delete only from `draft\|pending\|rejected`. Evidence additionally leaves the default set via supersession. |
| I16 | `origin.construction_work != null` => `origin.kind in {deinstallation, demolition}`. |
| I17 | `inherited_fields` and `inherited_from` are server-maintained: never accepted from a client except `inherited_fields` additions (re-inherit). `inherited_fields != []` => `inherited_from in parent_identities`. |
| I18 | `exit.construction_work` non-null => `exit.kind == installed`. `exit.kind in {split, merged, recycled, disposed}` => `reenter` rejected. `reserved` non-empty => `exit == null`. `past_cycles` never client-writable. |
| I19 | Identity hard `DELETE` only if no snapshot or evidence of it ever reached `published` (server checks `status` history: any `published`/`withdrawn` record => 409). `?purge=1` overrides, admin only, leaves a purge stub. `withdrawn.duplicate_of` must reference a non-withdrawn identity != self (no chains: re-point to the terminal). |
| I20 | `identity.dataset` references an existing `datasets._id`. At least one enabled user with `role == admin` exists (the last admin cannot be demoted or disabled). A dataset always has >=1 `moderator` member or is administered by admins only (allowed, warned). |
| I21 | Frozen snapshot fields and files (section 3.2.2) of a `published` snapshot reject PUT/PATCH/DELETE (409, pointing at `/supersede`). Derived fields are rejected from every client payload. A snapshot is superseded at most once; `supersedes` references a `published` snapshot of the same identity. |
| I22 | `verification.state == accredited` => exists `performed_by` actor with `accreditation.scope contains standard.code` and (`valid_until` null or >= `observed_at`). |
| I23 | `capture.markers` and `capture.fixtures` never satisfy I1 and are never read by a derivation (section 3.2.3). A `reinforcement_layout` record requires `position.snapshot_id` (its bar coordinates are in that snapshot's stored coordinates). |
| I24 | Evidence `attachments[]` of a `published` record: entries are never removed or reordered; a removal sets `removed {at, by_user_id, reason}` (`moderator(D)`, reason required) and deletes the file. `sha256` is computed server-side over the stored bytes. Same rule for snapshot photos after publish (section 3.2.2). |
| I25 | `identity.material` references an existing `materials._id`; `material_class_source == derived` => `material_class == materials[material].default_class` (recomputed when the material or its default changes); `assigned` values are never overwritten. |

---

## 6. Type x representation matrix

Rows are `shape_class`. "Primary proxy" = what stage 3 fits by default from a mesh or point
cloud. Descriptors follow existing applicability plus the new `applicable_shape_classes`.
Reviewed against 6.14 (decision 7.10):

- **Any class accepts any source** --- mesh, point cloud, or an authored primitive (the web
  wizard's L x W x H box, a GH extrusion). The class is derived *after* upload, so it cannot gate
  uploads.
- **An authored primitive, if present, is the primary proxy**: never refitted, no residuals, no
  deviation maps; frame and class are derived from it.
- The frame (`frame`, `bbx`) is not in this table: every class gets one from stage 1 (section 4.3).
- A visual inspection (`condition_grade`, decision 7.9) applies to every class.

| shape_class | primary proxy (from mesh / cloud) | fit | deviation maps | geometric descriptors | typical evidence |
|---|---|---|---|---|---|
| **linear** | `cylinder` if the mid-span section is circular (RANSAC inlier >= 0.9); else `prism` from the mid-span section if its residual is within tolerance; else `box` | ransac (cylinder), section + lsq (prism), obb (box) | n sides + 2 caps; lateral unroll for cylinder | scores, radial (frame centre-plane section, no rest align), HKS | rebound, core, cover, UPV, reinforcement layout |
| **planar** | `prism` (outline x thickness) | frame thickness + `shapely.concave_hull` outline (6.11) | top, bottom, n sides | scores, radial (silhouette, rest-aligned), HKS | rebound, core (slabs), visual, reinforcement layout |
| **block** | `box` | obb (+ lsq refine) | 6 faces | scores, HKS | rebound, mass, density |
| **irregular** | `hull` | hull | single spherical concavity map | scores, HKS, `sas_vectors` (dataset-specific, kept) | mass, density, visual |
| **composite** (assigned only, I4) | `box` of the whole | obb | 6 faces | scores on the whole | any |

Composite `part` proxies drawn by hand have no entry surface in 0.6 (neither web nor GH bridge)
--> later.

**Variable resolution** --- global LOD via `reduced` / `detailed` PLY and inline preview; the
proxy is the "container" (Bernhard's term) with `fit.source` as the link to the original. Local
relevance is expressed by `proxies[].regions[]` (section 3.2.1): a **schema slot only** in this release
--- authored or later derived, consumed by nothing yet. The viewer and GH keep fetching global
LODs. An adaptive remesh from proxy + deviation maps driven by regions is a later subproject.

---

## 7. API surface

Unchanged routes are not listed. Permissions are the section 7.0 table; `D` = the target's dataset.
`consumed_filter=active|consumed|all` becomes `circulation=active|exited|all` (default `active` =
`exit == null`), plus `?exit_kind=`. `type` query params become `original_function`;
`shape_class`, `material`, `material_class` and `dataset` are filters everywhere `type` was
accepted; list endpoints apply the visibility rule (section 3.6) and hide withdrawn identities unless
`?include=withdrawn`. `condition` filters and
sort keys are removed; `UpdateComponentSnapshotModel.condition` is removed; the frontend's
`conditionBadgeClass` / `conditionLabel` read from the fold instead (badge rule section 2.6; label 0
"unusable as is").

### 7.0 Permissions (decision 6.5)

Enforced **only** on the backend, by one dependency `require_dataset_role(dataset_of(target),
role)`; the frontend merely hides controls. `admin` passes every check. D = the target's dataset
(identity --> `dataset`; snapshot / evidence --> their identity's). "Author" = `added_by_user_id` /
`recorded_by_user_id`.

| action | who |
|---|---|
| read `published` / `withdrawn` (tombstone) records | visibility rule section 3.6 |
| read `draft` / `pending` / `rejected` | author; `moderator(D)`; `reviewer(D)` for pending evidence |
| create identity in D, snapshot, evidence | `contributor(D)` |
| edit a draft; submit `draft --> pending`; resubmit `rejected --> draft` | author |
| upload / replace / delete geometry files and photos | author or `moderator(D)`, **only while the snapshot is not `published`** (freeze rules: decision 6.6) |
| evidence attachments | unpublished record: author or `moderator(D)` add / remove; published: `contributor(D)` adds, `moderator(D)` removes with reason, tombstone entry kept (decision 7.3) |
| publish / reject / withdraw / reinstate (snapshot, evidence) | `moderator(D)` |
| promote `current_snapshot_id`; `effective_from`, `shape_class` overrides | `moderator(D)` |
| PATCH identity metadata (`origin`, `material`, `original_function`, `is_public`, ...) | `moderator(D)` |
| `exit`, `reenter`, `withdraw` identity | `moderator(D)` |
| move identity D1 --> D2 | `moderator(D1) and moderator(D2)` |
| set evidence `verification` | `reviewer(D)` |
| supersede published evidence | `contributor(D)` (new record enters `pending`) |
| reserve / release | any authenticated user who can read the piece |
| manage D's members, D's `visibility` / `name` / `description` | `moderator(D)` |
| create dataset; users; logs; `?purge=1`; actor redaction | `admin` |

### 7.1 Snapshots

```
POST   /identities/{id}/snapshots                  contributor(D): always creates status draft (immediate-promote branch removed)
POST   /snapshots/{sid}/supersede                  contributor(D): body = corrected snapshot; inherits effective_from (section 3.2.2)
POST   /snapshots/{sid}/submit                     author: draft --> pending      (replaces implicit pending on create); ?publish=1&promote=1 for moderators
POST   /snapshots/{sid}/publish                    moderator(D): pending --> published (+ ?promote=1 to set current_snapshot_id; replaces /validate)
POST   /snapshots/{sid}/reject                     moderator(D): pending --> rejected (+ reason; replaces DELETE-as-reject)
POST   /snapshots/{sid}/promote                    moderator(D): set current_snapshot_id to this published, non-superseded snapshot
POST   /snapshots/{sid}/withdraw                   moderator(D): published --> withdrawn (+ reason); names a replacement if it is current (section 3.1.4)
POST   /snapshots/{sid}/reinstate                  moderator(D): withdrawn --> published
DELETE /snapshots/{sid}                            author or moderator(D), only draft|pending|rejected (hard delete + files)
GET    /snapshots/pending                          moderation queue (replaces /pending-validation), filtered to the caller's moderated datasets
PATCH  /snapshots/{sid}                           per-field permission (section 3.2.2): draft --> author / moderator(D), everything but derived fields;
                                                  published --> moderator(D): mutable metadata, effective_from(+precision), shape_class / complexity override;
                                                  frozen field on a published snapshot --> 409 pointing at /supersede. Replaces PATCH /identities/{id}/current-snapshot
GET    /snapshots/{sid}/proxies/{i}/faces/{face}   deviation map PNG
GET    /snapshots/{sid}/capture/fixtures/{i}.ply   fixture mesh (section 3.2.3); visibility of the snapshot
POST   /snapshots/{sid}/proxies/recompute          moderator(D); runs section 4.3 for one snapshot
GET    /identities/{id}/timeline                   merged: past_cycles, origin, snapshot states + corrections, evidence, exit
POST   /identities/{id}/exit                       moderator(D); body = exit block (replaces POST /consume)
DELETE /identities/{id}/exit                       moderator(D); undo a mistaken exit (replaces /unconsume); not for server-set split/merge while children exist
POST   /identities/{id}/reenter                    moderator(D); body = new origin; archives {origin, exit} to past_cycles (section 3.1.3)
POST   /identities/{id}/withdraw                   moderator(D); body = {reason, duplicate_of?} (section 3.1.4)
POST   /identities/{id}/reinstate                  moderator(D); clears `withdrawn`
DELETE /identities/{id}                            author or moderator(D) while nothing was ever published (I19); ?purge=1 admin only
```

### 7.2 Evidence

```
POST   /identities/{id}/evidence                   contributor(D) --> status: draft (or pending with ?submit=1)
POST   /evidence/bulk                              contributor(D) of every target: [records] across one or more identities; validates all, inserts all or none (section 7.6)
GET    /identities/{id}/evidence                   ?method= ?tier= ?quantity= ?since= ?until= ?status= ?include=context,superseded
GET    /identities/{id}/properties                 identity block + outranked_evidence_ids; ?as_of=<iso> recomputes identity-scoped quantities over a time window (computed, not stored)
GET    /snapshots/{sid}/properties                 snapshot block (materialized as-of fold)
GET    /evidence/{eid}                             ?include=context; ETag/304
PATCH  /evidence/{eid}                             author while draft (all fields); moderator(D) after publish (`notes`, `position.description` only, I13)
DELETE /evidence/{eid}                             author, only in draft|pending|rejected (hard delete); published --> /withdraw (6.4)
POST   /evidence/{eid}/withdraw                    moderator(D): published --> withdrawn (+ reason); /reinstate reverses
POST   /evidence/{eid}/submit                      author: draft --> pending
POST   /evidence/{eid}/publish                     moderator(D): pending --> published; freezes; recomputes properties
POST   /evidence/{eid}/reject                      moderator(D): pending --> rejected (+ reason)
POST   /evidence/{eid}/supersede                   contributor(D): body = full new record; server links supersedes/superseded_by on publish; new record enters as pending
PUT    /evidence/{eid}/verification                reviewer(D): set state/by/at/note; I22 checked; recomputes properties
GET    /evidence                                   cross-catalog; ?dataset= ?method= ?quantity= ?min= ?max= ?status= ?verification=
GET    /evidence/pending                           moderation queue, filtered to the caller's moderated datasets
GET    /evidence/methods                           registry introspection
POST   /evidence/attachments                       multipart: one file + record_ids[] --- attaches one upload to several records (one stored copy per record, 7.3)
GET    /evidence/{eid}/attachments[/{index}]       list / download; visibility of the record
DELETE /evidence/{eid}/attachments/{index}         unpublished: author; published: moderator(D) + reason --> tombstone entry, file deleted
GET    /schema/evidence  /schema/create-evidence   codegen
```

Passport (`GET /identities/{id}/compose`) gains `identity.properties` (it is on the identity
document anyway) and an opt-in `?include=evidence`. Its shape follows this spec with no 0.5
aliases (section 8.0); 0.5 UserObjects are stopped by the client header (section 7.4) instead of being left to
misread it.

### 7.3 Public access

Anonymous readers of an `is_public` identity get `published`, non-superseded evidence only, with
actors projected to organization level. (CPR: free access for economic operators, clients, users
and authorities, Art 76(2)(e); levels of access, Art 76(2)(f); personal data, Art 77(1)(e).)
Photos served to anyone are EXIF-stripped at upload (section 3.5, decision 7.13).

### 7.4 Client identification (decision 6.7)

Every request carries `X-CSC-Client: <client>/<version>`, e.g. `gh-userobjects/0.6.0.0`,
`web/0.6.0.0`. The backend keeps a minimum-version table per client kind (`MIN_CLIENT_VERSIONS`
in settings). Missing header, unknown client, or version below minimum --> **426 Upgrade
Required** with a human-readable body naming the fix ("update via CSC_Update"). Exempt: the
updater itself (`/ghinterface/userobject*`, `/ghinterface/src*`), `/docs`, `/openapi.json`,
health. The web frontend sets the header in its API client (server- and browser-side). The
header is logged per request; it is identification for compatibility, **not** authentication.

### 7.5 Identifier resolution (decision 6.9)

```
GET /id/{uuid}      frontend route AND API route, permanent --- never renamed, never moved
```

- `Accept: text/html` (a phone that scanned a tag, a browser) --> 302 to the component page.
- `Accept: application/json` --> 302 to `/identities/{uuid}/compose` (the passport).
- Withdrawn with `duplicate_of` --> **301** to `/id/{duplicate_of}`; withdrawn without --> the
  tombstone page / JSON with `withdrawn`; purged --> **410**; unknown --> 404.
- Visibility rules (section 3.6) apply after the redirect, not before: resolution never leaks whether
  a members-only piece exists beyond a 404-equivalent for non-members.
- Scanners (`identify`, `locate-by-id`, `transmit-id`, GH) accept a raw UUID **or** any URL whose
  last path segment is a UUID --- so a future URL-bearing tag works with no code change.
- Later (additive): `/id/{scheme}/{value}` for `identifiers[]`.

### 7.6 Entry surfaces (decision 7.1)

Evidence enters through **one web form**, reached from the component page --- on a phone right
after a tag scan (`/id/{uuid}` --> component page --> *Add evidence*) or on a desktop. The method
picker drives a method-specific sub-form from the registry (section 4.5). Three shortcuts, all ending in
one `POST /evidence/bulk`:

| shortcut | what it does | typical use |
|---|---|---|
| fan-out | one submission --> several atomic records (rule 1.3) | 3 rebound test areas on one piece; one visual inspection noting spalling, cracking, corrosion |
| repeat from my last record | instrument, performers, standard, lab details prefilled from the user's latest record of the same method in the same dataset; dates default to now; readings / results always start empty | the next piece of a site survey; the next core from the same lab report |
| apply to several pieces | one claim --> one record per selected piece | an archival drawing or datasheet covering a whole batch of elements |

Field explanations are "?" popovers (tap on touch, hover/focus on desktop); their text is the
payload field descriptions served by `/evidence/methods` and `/schema/evidence`, never a
frontend copy.

**Files.** A shared file (one lab report for several cores) is uploaded once and attached to
every record the submission creates (`POST /evidence/attachments`, section 7.2). The visual-inspection
form takes photos **per observation** (decision 7.4): each fanned-out record gets the photos taken
for its observation; a photo showing several findings is attached to each. Inspection photos
document a finding and belong to the evidence record; **snapshot photos** stay a general
impression of the component, independent of its geometric representation. The camera / gallery
capture of the add-component wizard is reused.

**Position.** `kind: none` + `description` is always enough (section 3.3.2); optionally the user picks a
point on the 3D viewer (tap or click), which sets `position.snapshot_id` and `position.point`.

**Snapshots (decision 7.5).** One snapshot form --- the add-component wizard's details + photos
steps; geometry = an authored box from L x W x H --- reached from four places:

| entry point | reached from | creates |
|---|---|---|
| new component | scan an unused tag | identity + v0 |
| cut from ... | scan an unused tag, then the parent's tag(s) | child identity; server inherits (section 3.1.2) and sets the parents' `exit` split / merged (section 3.1.3) |
| record new state | component page | next version, `effective_from` = now unless set; only for a changed **shape** --- damage without shape change is evidence |
| correct | a published snapshot | superseding snapshot (section 3.2.2), prefilled, geometry kept unless dimensions are re-entered, same `effective_from` |

All four: `draft` --> photos --> `submit`; for a moderator, submit also publishes and promotes
(`?publish=1&promote=1`). The 0.5 edit form keeps only mutable metadata (`name`, `notes`,
`location`, `color`). **Deferred, planned:** mesh / point-cloud upload from the web (open: own
scanning app or import; source apps and formats; server-side processing of uploads).

Not in 0.6: spreadsheet-style entry sheet, CSV / lab-report import, GH evidence
components. There is no campaign entity (decision 7.2): the study is the dataset, the occasion is
stated by each record.

### 7.7 Datasets, materials, administration (decisions 6.4, 6.5, 6.10)

```
GET    /datasets                                   datasets the caller can see (section 3.6) + the caller's roles in each
POST   /datasets                                   admin; body = {_id slug, name, description, visibility (default members)}
PATCH  /datasets/{did}                             moderator(D): name, description, visibility (_id immutable)
PUT    /datasets/{did}/members/{user_id}           moderator(D): body = {roles: [...]}; empty set = remove
PATCH  /identities/{id}                            moderator(D) for metadata; changing `dataset` needs moderator of both (section 7.0)
GET    /materials                                  public: the controlled list (section 2.10)
POST   /materials                                  admin; `default_class` required (I25)
PATCH  /materials/{mid}                            admin; label, group, default_class, uniclass, notes (_id immutable); re-derives material_class
POST   /actors/redact                              admin; GDPR redaction (section 3.1.4)
```

The `/admin` web area gains dataset CRUD and a per-dataset member / role editor (decision 6.5)
and the materials list.

## 8. Migration from 0.5

### 8.0 Release path (decision 6.7)

| release | branch | contents |
|---|---|---|
| **0.5.1.0** | `v-0.5.1.0` | (a) backend logs `X-CSC-Client` (does not enforce); every GH UserObject sends `gh-userobjects/0.5.1.0`; shipped through `CSC_Update`. Purpose: at cutover, old clients are identifiable and stoppable. (b) **Runtime bump Python 3.9.18 --> 3.13** on Uberspace 7 (decision 6.12), isolated from any data-model change: new venv, `csc_env.yml`, README cron lines `python3.9` --> `python3.13`, `requirements.txt` + `constraints.txt` pinning the **glibc-2.17 ceiling** (`numpy<2.3`, `scipy<1.17`, `scikit-learn<1.8`, `robust-laplacian<1.1`; comment explains U7 = CentOS 7, newer wheels are manylinux_2_28). |
| **0.6.0.0** | `v-0.6.0.0` | this spec in backend + web frontend; header **enforced** (section 7.4); **GH bridge**: the UserObjects adapted to the new model with minimal workflow change (`type` input --> `original_function`, extrusion input --> authored prism proxy, salvage inputs --> `origin`, no client-side consume after split, create-as-draft + submit, header `gh-userobjects/0.6.0.0`). **Builder components** (decision 7.6): `Actor`, `Origin`, `IdentityMetadata`, `SnapshotMetadata` each output a JSON fragment of the API payload; `CreateComponentIdentity` / `CreateComponentSnapshot` take ID, dataset, metadata objects, geometry (+ parents) --- ~8 inputs instead of 22 / 16 --- and no longer compute PCA or reduce meshes (6.14). `MarkerPoints` and `Reinforcements` inputs removed (7.7, 7.8); **one evidence path**: `ReinforcementLayout` builder + generic `AddEvidence` (7.8). |
| after 0.6 | --- | full GH interface rebuild (Python or C# `.gha`), designed separately. |
| after 0.6 | --- | **Uberspace 8** (Arch, systemd) once out of public beta: lifts the constraints pins; supervisord `.ini` --> systemd units. MongoDB is on Atlas, unaffected. Infrastructure item, not in this spec. |

**No field aliases** survive into 0.6 (`type`, `extrusions`, `validated`, `consumed_at`,
`salvage_*`, `condition`): each would be semantically wrong under the new model, not merely
old. **`pca_frame` is renamed `frame`** (decision 7.10): the algorithm is no longer PCA, so the
old name would be wrong; `bbx` keeps its name (extents along the frame); `bbx_origin` (= `frame.o`)
is dropped. GH `ApplyPCAFrame` becomes `ApplyFrame`.

**Cutover:** 0.5.1.0 runs in production while 0.6 is built against migrated copies of the dumps.
At cutover the scripts below run on the then-current production dump; their
abort-on-unclassifiable guards catch drift since 260916. Minimum client version is set to
`0.6.0.0` in the same deploy.

### 8.1 Scripts

Scripts in `scripts/db_maintenance/`, each idempotent with `--dry-run`. All run at cutover
(section 8.0) on the then-current dump, **in the order of this table** (`run`); `after` names the
steps whose output a step reads. Step IDs are stable names (the decision log cites them), not
the order. Step 14 may also run on 0.5 once its upload pipeline strips EXIF; 11b runs after
cutover.

| run | step | script | after | what |
|---|---|---|---|---|
| 1 | 1 | `migrate_add_snapshot_effective_from.py` | --- | `effective_from = created`, precision `exact`, on all snapshots. 260916: 4 identities have a v1; `created` is monotonic in `version` for all of them --- the script asserts that and aborts otherwise. |
| 2 | 1b | `migrate_snapshot_validated_to_status.py` | 1 | `validated: true --> status: published`; `false --> pending`; drop `validated`. Rejected 0.5 snapshots were deleted, so none map to `rejected`. |
| 3 | 1c | `migrate_init_06_fields.py` | 1b | initialise every new field to its empty value so no reader meets a missing key: snapshots `supersedes` / `superseded_by` / `status_changed_*` = null, `capture` = null, `effective_from_precision` from step 1; identities `withdrawn` = null, `past_cycles` = [], `properties` = {}; later steps overwrite where they have data. |
| 4 | 9 | `migrate_drop_snapshot_fields.py` | --- | `$unset` `processes` (empty in all 701) and `assembly` (false in all 701) --- 6.13; `virtual` (false in all 701) --- 7.12; `iframe` (always identity) --- 7.11. Aborts if any snapshot has `virtual: true`. |
| 5 | 2 | `migrate_rename_measurements_collection.py` | --- | drop the empty `component_measurements`; bind `component_evidence`. |
| 6 | 11 | `migrate_datasets_collection.py` | --- | create the 7 `datasets` docs from distinct `identity.dataset` values, `members: []`. Visibility: `catalog` for `mineral_composite_panels`, `sas_cita_scans`, `ddu_build_with_debris`, `ddu_aggregations`; `members` for `dbu_zirkus`, `schoenes_neues_feld`, `spa_example_data`. `admin` stays global admin. Memberships are **not** migrated --- assigned afterwards by admin through the extended user-administration frontend (deliverable: dataset CRUD + per-dataset member/role editor under `/admin`). |
| 7 | 12 | `migrate_material_vocab.py` | --- | seed `materials` (section 2.10); map `corian --> mineral_composite` + `trade_name: "Corian"`, `concrete --> concrete`, `brick --> fired_clay`, `aerated-concrete --> autoclaved_aerated_concrete`, `asphalt --> asphalt`, `steel --> steel`, `wood --> timber`; derive `material_class` (`derived`). Aborts on any unmapped value. Runs before 10b (inheritance compares `material`/`trade_name`). |
| 8 | 3 | `migrate_type_to_original_function.py` | --- | `panel-->IfcPlate`, `beam-->IfcBeam`, `column-->IfcColumn`, `slab-->IfcSlab`, `brick-->IfcBuildingElementPart` (6.13; no 0.5 identity uses it), `pipe-->IfcPipeSegment`, `profile-->IfcMember`, `connector-->IfcDiscreteAccessory`, `rubble-->CscDebris`, `other-->IfcBuildingElementProxy`. Drops `type` (no alias, section 8.0). |
| 9 | 10 | `migrate_salvage_to_origin.py` | --- | Hand-mapped, not string-copied --- the 0.5 data holds only 4 distinct `salvage_source` values (table below). `salvaged_at` --> `origin.at`, precision `day` (all stored values are midnight). Identities with no salvage data get `origin.kind` from their dataset (table below). Drops `salvage_source`, `salvaged_at`. |
| 10 | 10c | `migrate_consumed_to_exit.py` | --- | 42 consumed identities (260916): the 37 split parents --> `{kind: split, at: consumed_at, precision exact, recorded_by_user_id: null}`; 5 `ddu_build_with_debris` --> `{kind: installed, notes: "modified by students during the workshop; resulting pieces not catalogued"}`; 1 `ddu_aggregations` --> `{kind: lost, notes: same}`. `at` = `consumed_at`. All others `exit: null`, `past_cycles: []`. Drops `consumed_at`. Script asserts the 37/5/1 split and aborts on any consumed identity it cannot classify. |
| 11 | 10b | `migrate_lineage_inheritance.py` | 3, 10, 12 | after 3 and 10. For every identity with `parent_identities`: set `inherited_from`; for each inheritable field equal to the parent's value --> list it in `inherited_fields`. **`manufactured_at` on the 45 children holds their creation timestamp (GH wrote it)** --> overwrite with the parent's (all `unknown`) and list it as inherited; the cut moment survives as the child's first-snapshot `effective_from` (step 1). Roots get `inherited_fields: []`, `inherited_from: null`. |
| 12 | 6 | `migrate_attributes_cleanup.py` | 1c | `attributes.primitive` --> dropped (now derivable); `attributes.scan` --> `capture.notes`; `attributes.3d_scan_metadata` --> `capture{method: photogrammetry, captured_at, device, software}` **on the identity's v0 snapshot** (7.7); local paths dropped. |
| 13 | 6c | `migrate_capture_context.py` | 6 | the 70 `ddu_build_with_debris` snapshots (7.7): `geometry.marker_points` --> `capture.markers` --- labels re-read from the source OBJs (`marker_blue_*`, `marker_green_*`) if still on disk, else by position (the +/-120 mm cross at z ~ 0 --> `role: rig`, the rest --> `role: component`); `meshes[1]` (`end_effector`) --> `capture.fixtures[0]`, its `detailed.ply` moved to `capture/<sid>/fixtures/0.ply`, inline copy and `reduced.ply` dropped, `mesh_ply_resolutions["1"]` removed; `capture.coordinate_system = {name: "DDU robot gripper marker plane"}`. Drops `geometry.marker_points`. Asserts every moved mesh is the effector (bbox +/-145 mm around the marker plane). |
| 14 | 6d | `migrate_reinforcements_to_evidence.py` | 2 | the 1 snapshot with `geometry.reinforcements` (dbu_zirkus, 35 bars): one `reinforcement_layout` record (7.8) --- `basis: drawing` (user: the bars were modelled after the original drawing), bars copied, `position.snapshot_id` = that snapshot, `status: published`, `verification: unverified`, `observed_at` = snapshot `created` (day), `recorded_by` = snapshot author. Drops `geometry.reinforcements`. |
| 15 | 6b | `migrate_condition_to_evidence.py` | 2 | **only grades from datasets where they vary** (decision 7.9; 260916: `schoenes_neues_feld`, 5 snapshots) --- a value uniform across a dataset is a batch default and is dropped (698 x `2`); the script prints the per-dataset table and takes an override list. Each migrated snapshot --> one `component_evidence` record: `method: visual_inspection`, `summary: {condition_grade, value, ordinal, claimed}`, `source_tier: visual`, `status: published`, `verification: unverified`, `performed_by: [{kind: user, user_id: added_by_user_id}]`, `observed_at: snapshot.created` (precision `day`), `position: {kind: none, snapshot_id}`. Then drop `condition`. |
| 16 | 4 | `migrate_extrusions_to_proxies.py` | --- | each `geometry.extrusions[i]` --> `proxies[i] = {primitive: prism, role: primary if i==0, params: {profile, height}, placement: the extrusion's own placement, fit: {method: authored}}`. Remove `extrusions`. |
| 17 | 9b | `migrate_complexity_source.py` | --- | `sas_cita_scans` (71): keep value, `complexity_source: assigned`. All others (630, batch defaults): `complexity_source: derived`, value recomputed by stage 5 of `main_geometry.py`. |
| 18 | 5 | `main_geometry.py --stages frame,shape_class --recompute` | 3, 4, 6c | every snapshot gets `frame` + `bbx` by the 7.10 rule (min-volume box, axis convention); `pca_frame` and `bbx_origin` `$unset`. Replaces the planned `migrate_obb_to_box_proxy.py` --- the frame is no longer a proxy. Prints, per dataset, how many frames changed axis order vs. 0.5 (expected: diagonal cases, columns). **Must run after 4 (authored prisms), 6c (gripper leaves `geometry`) and 3 (column rule reads `original_function`).** |
| 19 | 7 | `main_geometry.py --stages proxies,descriptors,complexity,previews --recompute` | 5, 9b | fits, residuals, deviation maps, descriptors (frame-aligned, version bump), complexity, previews (6.14). |
| 20 | 8 | `main_geometry.py --stages shape_class,frame --recompute` | 7 + threshold tuning | after tuning and once scores exist: final `shape_class` (`derived`), then the frame again where the class changed (column rule, 7.10). |
| 21 | 13 | `migrate_archive_designs.py` | --- | decision 7.11: export the whole `designs` collection to `designs_archive_<yymmdd>.json` next to the cutover dump, verify the document count, then drop the collection. |
| 22 | 14 | `migrate_strip_photo_gps.py` | --- | decision 7.13: re-save every stored snapshot photo without GPS / owner / serial (orientation, capture time, make / model kept); prints how many files carried GPS (260916 assets: 3 of 8). Independent of 0.6 --- can run as soon as the upload pipeline strips too. |
| post | 11b | `migrate_retire_shared_account.py` | cutover done, personal accounts exist | **after personal accounts exist.** Input: a mapping file (`dataset` or explicit snapshot/identity id list --> personal `user_id`). Rewrites `added_by_user_id`/`added_by_username` on snapshots (and `recorded_by_*` on migrated evidence, `performed_by` user actors), keeping `attribution_corrected: {from_user_id, at, by_user_id}` on each touched document so the correction is auditable. Adds the mapped users as `contributor` of the datasets they authored. Then sets `ddu.disabled = true` --- never deleted, it is still referenced by `attribution_corrected`. Refuses to run while any record still points at `ddu` without a mapping. |

Step 10 mapping (dump 260916):

| 0.5 `salvage_source` | n | --> `origin` |
|---|---|---|
| `Rosskopf + Partner AG, Bahnhofstrasse 16, 09573 Augustusburg` | 521 (477 `mineral_composite_panels` + 44 split children in `ddu_aggregations`) | `kind: offcut`, `at: 2022-10-26` (day), `place: {name: "Rosskopf + Partner AG", address: "Bahnhofstrasse 16, 09573 Augustusburg"}`, `performed_by: [{kind: organization, name: "Rosskopf + Partner AG", role: ...}]` |
| `ExFeld Architektur, TU Darmstadt` | 4 (`schoenes_neues_feld`) | `kind: unknown`, `at: 2026-05-19` (day), `place: {name: "ExFeld", address: "TU Darmstadt"}` --- ExFeld is the location, not an institution; `performed_by: []` |
| `Guenther Behnisch Strasse, TU Darmstadt Lichtwiese Campus, 64287 Darmstadt, Germany` | 1 (`dbu_zirkus` beam) | same as the `dbu_zirkus` row below |
| `Measured by Hand, Parent not found (ID:69da...)` | 1 | `kind: unknown`, string --> `origin.notes` |
| *(none)* `sas_cita_scans` | 71 | `kind: demolition`, rest null |
| *(none)* `ddu_build_with_debris` | 70 | `kind: demolition`, rest null |
| *(none)* `spa_example_data` | 9 | `kind: unknown` |
| *(none)* `ddu_aggregations` without parent | 5 | as the Rosskopf row (`offcut`) |
| all 16 `dbu_zirkus` | 16 | `kind: deinstallation`, `place: {name: "TU Darmstadt Lichtwiese Campus", address: "Guenther-Behnisch-Strasse, 64287 Darmstadt, Germany"}`, `construction_work: {name: "Lichtwiese Campus Infrastructure --- pedestrian bridge", use: "pedestrian bridge"}`, `at: 2024-07-24` (day) --- one deinstallation for all 16 (user, 2026-09-28) |

Frontend: regenerate models; replace every `type` and `extrusions` consumer. Grasshopper: bump
all UserObjects (breaking).

---

## 9. Decided questions (carried through grilling)

Every question raised during grilling, with the decision that closed it. (Number 3 was never
assigned in the first draft; the numbering is kept so older references stay valid.)

1. *(decided 6.5: `reviewer` is a per-dataset membership role, orthogonal to `moderator`)*
2. *(decided 6.11: no new dependency; in-house RANSAC on numpy)*
4. *(decided 6.13: `IfcBuildingElementPart`)*
5. *(decided 6.13: `processes` and `assembly` removed)*
6. *(decided 6.13: merges --> union of ranges, weakest confidence x k)*
7. *(decided 6.10: controlled `materials` collection + LoW ch. 17 class + `trade_name`)*
8. *(decided 6.13: `email` only admin + moderator(D))*
9. *(decided 7.1: one web form from the component page --- fan-out, repeat-from-last, multi-piece; no sheet, no CSV import, no GH evidence component in 0.6. Decided 7.2: no campaign concept, `campaign_id` dropped)*
10. *(decided 6.7: 0.6.0.0 on `v-0.6.0.0`; no aliases; client header; GH bridge in 0.6)*
11. *(decided 6.14: one runner, ordered stages, cheap stages synchronous)*
12. *(decided: `condition` dropped; see section 2.6 `condition_grade`, section 8 6b)*
13. *(decided 6.1, 6.4, 6.8, 6.9: CPR proposals triaged --- see section 10.5)*
14. *(decided 6.15: `complexity` derived + overridable; sas_cita ratings = tuning labels)*
15. *(decided 7.13: strip GPS / owner / serial at upload, keep orientation, capture time, make /
    model; one-off cleanup of stored photos --- 3 of 8 in the 260916 assets carried GPS)*

---

## 10. EU Construction Products Regulation & Digital Product Passport compatibility

Source: **Regulation (EU) 2024/3110** (recast CPR, in force 7 Jan 2025), Chapter X (Arts 75--80),
Art 3 definitions, Arts 14--15, 18, 21--22, 26, Annexes I, II, IV, V, VII; it delegates identifiers,
registry and portal to **Regulation (EU) 2024/1781** (ESPR) Arts 12--14. The construction DPP system
itself arrives by delegated act (Art 75(1)); mandatory use follows 18 months after that act
(Art 80(1)). Everything below is therefore *alignment*, not compliance: CSC should be able to
**emit** a passport-shaped record, not *be* one.

### 10.1 Where CSC stands in the regulation

| CPR concept | text | CSC reading |
|---|---|---|
| Used product | Art 3(20): not waste, installed at least once, and either (a) only checked/cleaned/repaired or (b) transformed in a way *non-essential* to performance | every CSC identity |
| Remanufactured product | Art 3(25): transformed in a way *essential* to performance | a CSC identity after a cutting / re-engineering snapshot chain, once a harmonised spec says the transformation was essential |
| Placing on the market | Art 3(5): "the first making available on the Union market of a used product **after a deinstallation**" | a CSC component handed to a reuse project --- unless directly reused |
| Direct reuse carve-out | Recital 34: "products directly reused in a construction work should not be considered as placed on the market again" | the research/prototype path stays outside the regulation |
| Who becomes the manufacturer | Art 26(2): whoever places a used or remanufactured product on the market takes on Art 22 obligations (DoPC, CE, DPP) | not CSC itself; **the operator who lists a piece for reuse** --- CSC is their documentation tool |
| Rights vs. deinstaller | Art 21(3): that manufacturer may demand "information about the previous use of the product and about the process of deinstalling it" | CSC must be able to record the deinstallation *process*, not just a date |
| Life cycle of a used product | Art 3(53): starts "from the latest deinstallation from the construction work" | CSC's timeline origin for LCA is the deinstallation date |
| 3D-dataset | Art 3(11): "a set of numerical data describing the shape of an object by its outer dimensions and its cavities" | a CSC snapshot geometry, in the regulation's own words |
| Product type | Art 3(27): "the abstract model of individual products ... which exclude any variation with regard to performance" | **the impedance mismatch** (section 10.2) |

### 10.2 The product-type mismatch

The CPR and the DPP are built on *product types* (one passport per type, serial/batch optional,
Art 22(5), Annex V 1(a)). A reclaimed element is unique: each identity is a product type of one.
Consequences, and how CSC absorbs them:

- **Unique identification code of the product type** (Art 22(5), 18(2)(d)) <-> `catalog_number`
  (`CSC-000042`) --- human-facing, monotonic, never recycled, already on the QR label.
- **Batch or serial number** <-> `identity._id` (UUID); a `snapshot.quantity > 1` batch is the one
  case where several physical items share a type.
- **Persistent unique identifier + data carrier** (Art 77(1)(a--c), 79(1) --> ESPR Art 12: identifiers
  per ISO/IEC 15459, data carrier per ISO/IEC 15459 too) --- CSC's UUID is *persistent* but not
  ISO/IEC 15459. **Decided (6.9):** the data carrier (QR/NFC tag) keeps encoding the **raw
  UUID** --- host-independent by construction; no domain can be guaranteed forever. Resolvability
  is a *server* capability, not a label property: the permanent route `/id/{uuid}` (section 7.5).
  Moving hosts = DNS / redirect, never relabelling. ESPR compatibility later = (a) an
  `identity.identifiers[]` slot `{scheme: "gs1_sgtin" | "espr" | "din_spec_91484" | ..., value,
  issued_by, issued_at}` (deferred, additive), (b) `/id/{scheme}/{value}` resolving those, (c) if a
  regulation ever demands a URL carrier, a second tag whose URL still ends in the same UUID.
- **Declared use** (Art 3(22), Annex V 1(c)) is set by the manufacturer *at placing on the market*
  --> an export-time / design-time field, never on the identity (same reasoning as
  `original_function`, section 2.1).

### 10.3 Field-level mapping --- DPP content (Art 76(2)(a)) --> CSC

| CPR requirement | CSC field / mechanism | status |
|---|---|---|
| Annex V 1(a) unique ID code + serial | `catalog_number` + `_id` | exists |
| Annex V 1(b) product category / **Annex VII product family** | `identity.cpr_product_family` (int 1--36), derived from `original_function` x `material` (concrete --> 1 or 26; steel --> 20; timber --> 13; masonry --> 17; **rubble/aggregate --> 24**; prefabricated elements --> 34), overridable | **deferred** (additive, 6.8) |
| Annex V 1(d) nominal dimensions | `bbx` --- extents along the snapshot `frame` (section 4.3 stage 1); primary proxy `params` for the shape | **in 0.6** |
| Annex V 1(f) estimated service life (durability) | quantity `service_life` (years, identity scope, tiers archival/heuristic) | **deferred** (additive, 6.8) |
| **Annex V 1(h) "date and place of the latest deinstallation"** | `identity.origin` (section 3.1.1) when `origin.kind == "deinstallation"`; empty otherwise. Covers Art 21(3) (`method`) and Art 18(2)(a) (`at` at `year` precision). Named `origin`, not `deinstallation`, because most of the 0.5 catalogue was never installed (offcuts, demolition rubble) --- calling it deinstallation would be false | **decided (6.1)** |
| Annex V 7 certificates / validation reports from notified bodies | evidence `attachments[]` (7.3) + `performed_by[]`; `actor.accreditation {scheme: iso_17025 \| notified_body, id, body, scope, valid_until}` makes accreditation machine-checkable and gates `verification.state: accredited` (I22) | **in 0.6 (6.8)** |
| Annex V 9(a--b) declared performances: one value / level / class per essential characteristic, or `NULL` | the `properties` fold, projected: each quantity carries `cpr_essential_characteristic: {standard, name, kind: level\|class}`; projection rule = **conservative bound of the range** (lower bound for strength, upper for hazard), `NULL` when no evidence. The catalog *proposes*, the manufacturer declares | fold **in 0.6**; mapping + projection **deferred** (6.8) |
| Annex V 9(c) + Annex II: 19 environmental essential characteristics (climate change total/fossil/biogenic/LULUC, ozone, acidification, eutrophication x3, POCP, ADP x2, water, PM, radiation, ecotox, human tox x2, land use), phased 2026/2030/2032 | a quantity family `env_*` (identity scope), source tier **`calculated`** (new tier: values from an LCA tool / Oekobaudat, not observed), life cycle starting at `origin.at` when `origin.kind == deinstallation` (Art 3(53)) | **deferred** (additive, 6.8) |
| Annex IV 1.2(e) main materials used | `material` + `material_class` (EU List of Waste ch. 17) + `trade_name` (section 2.10); `secondary_materials[]` deferred | **decided (6.10)** |
| Annex IV 2.7 recommendations for repair / deinstallation / reuse / remanufacturing / recycling | `identity.reuse_guidance` free text, or an evidence kind `expert_recommendation` | **deferred** (additive, 6.8) |
| Art 22(3) technical documentation | passport (`compose`) + evidence + snapshots + provenance graph --- *is* the technical documentation | exists |
| Art 76(2)(a)(vii) data carriers of **key parts** (Art 3(16)) | a `composite` snapshot's `part` proxies, or child identities via `parent_identities` | exists in principle |
| Art 3(20)/(25) used vs. remanufactured | `identity.processing_level in {checked_cleaned_repaired, non_essential_transformation, essential_transformation, unknown}` --- assigned (the essential/non-essential call depends on the harmonised spec), with the snapshot chain as the evidence | **deferred** (additive, 6.8) |

### 10.4 System-level requirements the design already meets or must meet

| CPR / ESPR requirement | CSC design response |
|---|---|
| Art 77(1)(d) open standards, machine-readable, structured, searchable, transferable, no vendor lock-in | JSON Schema at `/schema/*`, UCUM units, IFC-name vocabularies, Uniclass codes; IFC/IfcOpenShell export as a projection |
| Art 75(2)(a) interoperable with **BIM** | `original_function` = IFC class names; proxies map to `IfcExtrudedAreaSolid` (prism/box/cylinder) and `IfcTriangulatedFaceSet` (mesh); properties export as a PSet |
| Art 75(2)(c), 76(2)(f), 78(f) tiered access rights per actor class | `is_public` + auth + `reviewer` + admin/moderator; `status == published` is the public tier |
| Art 77(1)(e) no end-user personal data without GDPR consent | actor projection: organization-only for anonymous readers (section 3.3.1); `email` never in lists |
| Art 78(h) data authentication, reliability, integrity | `etag` hashes; supersession instead of edits (section 3.3.4); server-recomputed derived values; signed evidence records **deferred** (additive, 6.8) |
| Art 75(2)(i) system available **25 years** after last placing; operator keeps passport >= **10 years** | **retention rule:** `published` snapshots and evidence are never hard-deleted --- `DELETE` becomes a tombstone (`status: withdrawn`, reason, by, at) that keeps the document and its files. Draft/pending/rejected may be hard-deleted. Identities are never deleted: they `exit` (section 3.1.3) |
| Art 75(2)(e) arrangements for **updating** the passport of an existing product | snapshot versions + evidence supersession + fold recompute --- the update model is the whole point of section 3--4 |
| Art 75(2)(j) "availability of information for the reuse and remanufacturing of products" | CSC's purpose; the timeline (section 7.1) is the human-readable form |
| Art 15(2) environmental performance calculated with Commission software | out of scope for CSC; the `env_*` quantities are inputs/outputs of that step, tier `calculated` |
| Art 14 exemption: custom-made / non-series products installed by the manufacturer in a single identified work | most research reuse projects fall here --> no DoPC, no DPP obligation --- but the record should still be exportable |

### 10.5 What this changed in the spec (triaged, decision 6.8)

1. ~~`identity.salvage_source` + `salvaged_at` --> `identity.deinstallation {...}`~~ **Decided
   (6.1), modified:** --> `identity.origin {kind, ...}` (section 3.1.1, section 2.8); maps to the CPR deinstallation
   fields only when `kind == deinstallation`.
**Triage rule (6.8):** breaking-or-rework-to-add-later --> 0.6; purely additive --> deferred.

2. `identity.identifiers[]` slot (section 10.2) --- **deferred** (additive). Tags keep the raw UUID;
   resolver `/id/{uuid}` **in 0.6** (6.9, section 7.5).
3. `identity.cpr_product_family` (derived, overridable) and `identity.processing_level` (assigned)
   --- **deferred** (additive; `origin.kind` + snapshot chain carry most of it meanwhile).
4. ~~`actor.notified_body_id`~~ --> `actor.accreditation {scheme: iso_17025 | notified_body, ...}`;
   `accredited` requires it (I22) --- **in 0.6** (adding the rule later would invalidate records).
5. Quantity vocabulary: `cpr_essential_characteristic` mapping column; `service_life`; `env_*`
   family with new source tier `calculated` --- **deferred** (additive: one evidence method +
   vocabulary rows).
6. Retention: tombstones --- **in 0.6** (decided 6.4).
7. A `GET /identities/{id}/export?format=cpr-dpp` projection (JSON, Annex V structure) ---
   **deferred** until the delegated act fixes the data dictionary (Recital 92).

### 10.6 The wider EU product-passport landscape (researched 2026-09-12)

The CPR does not define its passport's plumbing; it inherits it. What CSC must track, in order
of how directly it binds:

| instrument | status (Sep 2026) | what it fixes | CSC consequence |
|---|---|---|---|
| **ESPR --- Reg. (EU) 2024/1781**, Arts 9--15 + Annex III | in force; DPP registry to be set up by the Commission by **19 Jul 2026** (Art 13); product-group delegated acts pending | the DPP *framework*: data requirements, unique product / operator / facility identifiers (Art 12), registry (Art 13), web portal (Art 14). CPR Art 79 applies these to construction products | `identifiers[]` (section 10.2) must hold an ESPR-registry-issued identifier once it exists; the QR on the piece is the ESPR data carrier |
| **EN 182xx family --- CEN/CLC JTC 24** ("Digital product passport: framework and system", standardisation request M/604) | first six published **27 May 2026**, cited in the OJ **15 Jul 2026** (Implementing Decision (EU) 2026/1736); two still to be cited | EN 18216 data exchange protocols ; **EN 18219 unique identifiers** ; **EN 18220 data carriers** (optical 2D, RFID, NFC) ; **EN 18221 data storage, archiving, persistence** ; **EN 18222 APIs for passport lifecycle management and searchability** ; EN 18223 system interoperability ; EN 18239 access rights, security, confidentiality ; EN 18246 data authentication, reliability, integrity | these are the *technical* targets for section 10.4: identifier syntax (18219), QR payload (18220), retention (18221 --- the 25-year rule made concrete), the API surface an export must speak (18222), tombstones + hashes (18246). **Obtain 18219/18220/18221/18222 before implementing `identifiers[]` and the export.** |
| **CIRPASS-2** (Digital Europe, May 2024 -- Apr 2027) | running; 13 lighthouse pilots, one of them **construction, led by Cobuilder** | the reference pilot for a construction DPP; will produce the de-facto data model the delegated act inherits | watch item; the pilot's construction data model (Cobuilder's "Define"/bSDD-based dictionary) is the likeliest shape of Recital 92's "common data dictionary" |
| **EN 15804+A2** (EPD core rules) | established | the 13 core + 6 additional environmental indicators | **CPR Annex II (a)--(m) = the 13 core, (n)--(s) = the 6 additional --- a 1:1 match.** The `env_*` quantities (section 10.3) should carry EN 15804 indicator codes (GWP-total, GWP-fossil, GWP-biogenic, GWP-luluc, ODP, AP, EP-freshwater, EP-marine, EP-terrestrial, POCP, ADP-minerals&metals, ADP-fossil, WDP; PM, IRP, ETP-fw, HTP-c, HTP-nc, SQP) as their `unit`-adjacent identifier. Used products: modules from the latest deinstallation only (Art 3(53), Recital 36). Data source candidates: Oekobaudat (already in `FUTURE.md`), ISO 22057 EPD data templates |
| **EPBD --- Dir. (EU) 2024/1275** | renovation-passport schemes by **29 May 2026** (Annex VIII); digital building logbooks where available; whole-life-carbon disclosure per EN 15978 / Level(s) 1.2 | the *building-side* twin of the product passport: what the piece is deinstalled *from* and installed *into* | `origin.construction_work.identifier` / `exit.construction_work.identifier` (section 3.1.1) should be able to carry a building identifier that a digital building logbook would recognise; a design's WLC (computed outside CSC, 7.11) needs each component's `env_*` |
| **Level(s)** (EU building sustainability framework) | established, voluntary | indicator 1.2 life-cycle GWP, 2.1 bill of quantities/materials, 2.4 design for deconstruction & reuse | CSC components are exactly Level(s) 2.4's input; a GH definition over fetched catalog data could produce a 2.1 bill of materials (designs are not stored in CSC, 7.11) |
| **Battery Reg. (EU) 2023/1542** | battery passport mandatory **Feb 2027** | the first live DPP --- the working reference for registry, access tiers, QR resolution | implementation patterns only; no data overlap |
| **Waste Framework Dir. 2008/98/EC** | established | end-of-waste: a piece is a *product* only if it "is not waste or has ceased to be waste" (Art 3(20)/(25)) | `origin` should be able to record the end-of-waste basis (never waste / ceased to be waste + reference) --- **deferred** (additive optional field on `origin`, 6.8) |
| **DIN SPEC 91484:2023** | published; German, voluntary | pre-demolition audit data set for reusable products | national precursor of Annex V 1(h) + Annex IV; cross-check pending (section Sources) |

Not yet law, watch: the Commission's announced **Circular Economy Act** (expected 2026) and any
CPR delegated act under Art 75(1) --- the latter is the single event that turns section 10 from
alignment into obligation, and starts the Art 80 clocks (system live +6 months, obligations
+18 months).

**Practical reading for CSC:** the identifier, data-carrier, persistence and API standards now
exist as ENs; the construction-specific data dictionary does not. So: build to EN 18219/18220/
18221/18222/18246 now (they are stable and cited), keep the field vocabulary IFC/EN 15804/UCUM-
based so it can be mapped when the dictionary lands, and treat the CIRPASS-2 construction pilot
as the early signal for that dictionary.

---

## Appendix A --- Evidence payloads

All payload models: `extra = "forbid"`. Server recomputes and cross-checks marked fields.

### A.1 `rebound_hammer` (EN 12504-2:2021 / ASTM C805)

```jsonc
{
  "instrument": {
    "hammer_type": "N" | "L" | "NR" | "LR" | "Q_N" | "Q_L",
    "manufacturer": "...", "model": "...", "serial": "...",
    "impact_energy_nm": 2.207,
    "last_calibration_at": "2026-01-15",
    "anvil_check": { "performed_at": "...", "value": 80, "expected": 80, "correction_factor": 1.0 } | null
  },
  "test_area": {
    "label": "TA-1",
    "surface_preparation": "ground" | "as_found",
    "surface_condition": "dry" | "damp" | "wet",
    "carbonation_depth_mm": null, "surface_temperature_c": 14.0,
    "min_spacing_mm": 25, "min_edge_distance_mm": 25
  },
  "impact_direction": "horizontal" | "vertically_down" | "vertically_up" | "inclined",
  "impact_angle_deg": null,
  "readings": [44, 42, 41, 45, 43, 42, 40, 44, 43],      // all, in order
  "reading_unit": "1" | "Q",
  "rejected_reading_indices": [],                          // flagged, never deleted
  "outlier_policy": "en_12504_2" | "astm_c805" | "none",
  "set_discarded": false,                                  // server: EN rule >20% deviate >25% from median
  "n_valid": 9,
  "median": 43,                                            // server-computed, whole number
  "direction_correction_applied": false
}
```

Validation: `len(readings) >= 9` when standard is EN 12504-2 (`>= 10` for ASTM); `median` and
`set_discarded` recomputed server-side and must match; `reading_unit == "Q"` <=>
`hammer_type in {Q_N, Q_L}`; `summary.quantity` = `rebound_number` or `q_value` accordingly;
**never** a strength. Strength estimates go in `derived[]` with a named model.

### A.2 `core_compression` (EN 12504-1:2019, EN 12390-3:2019 / ASTM C42, C39)

```jsonc
{
  "sampling": {
    "cored_at": "...",                                      // --> envelope sampled_at
    "drill_diameter_mm": 100, "drilling_method": "wet" | "dry",
    "orientation_vs_casting": "perpendicular" | "parallel" | "unknown",
    "operator": { /* actor */ } | null,
    "hole_repaired": false
  },
  "specimen": {
    "label": "C-03",
    "measured_diameter_mm": 99.6,
    "length_as_drilled_mm": 215.0, "length_prepared_mm": 199.2,
    "end_preparation": "ground" | "capped" | "sawn" | "none",
    "length_diameter_ratio": 2.0,                         // server-computed
    "ld_class": "2:1" | "1:1" | "other",                  // server: 2:1 iff 1.95--2.05
    "mass_g": 3712.0, "density_kg_m3": 2382.0,
    "moisture_condition": "as_received" | "water_saturated" | "air_dried",
    "reinforcement_present": false, "reinforcement_note": null,
    "defects_note": null
  },
  "test": {
    "tested_at": "...",                                     // --> envelope observed_at
    "machine": { "manufacturer": "...", "model": "...", "serial": "...", "class": "EN 12390-4", "last_calibration_at": "..." },
    "loading_rate_mpa_s": 0.6,                            // warn outside 0.4--0.8
    "max_load_kn": 298.4, "cross_section_area_mm2": 7791.0,
    "failure_type": "satisfactory" | "unsatisfactory", "failure_type_code": null,
    "age_at_test_days": 7
  },
  "result": {
    "fc_core_mpa": 38.3,                                  // server: F/A within 1 %
    "ld_correction_applied": false,
    "fc_is_cyl_mpa": 38.3 | null, "fc_is_cube_mpa": null,
    "conversion_basis": "EN 13791" | null
  }
}
```

`summary` = `{compressive_strength, fc_core_mpa, MPa, measured}`. In-situ conversions go in
`derived[]`. `reinforcement_present: true` --> UI warning, not rejection. Context resolves at
`sampled_at`.

### A.3 Non-instrumental kinds

```jsonc
// archival_document
{ "document": { "title": "...", "date": "1968-03", "kind": "drawing" | "spec" | "report" | "photo" | "other", "reference": "..." },
  "claim": { "text": "B225", "interpretation": "..." } }
// summary: {concrete_class, range: ["B225"], claimed}  or  {compressive_strength, range:[18,28], MPa, claimed}

// visual_inspection
{ "observations": [ { "quantity": "spalling", "value": 1, "note": "..." } ] }   // value = severity 0--3 for findings, grade 0--3 (3 good) for condition_grade (section 2.6)
// summary: {spalling, value: 1, ordinal, claimed}   --- one evidence record per observed quantity (atomic rule)
// inspection photos are this record's attachments (decision 7.4), never snapshot photos; `photos_attached` removed (derivable)

// era_heuristic
{ "basis": "construction_year" | "region_practice" | "typology", "year": 1968, "source": "..." }
// summary: {compressive_strength, range:[18,28], MPa, claimed}

// manufacturer_datasheet
{ "manufacturer": "...", "product": "...", "reference": "..." }
```

### A.4 `reinforcement_layout` (decision 7.8)

```jsonc
{
  "basis": "drawing" | "scan" | "exposed",            // --> source tier: archival | ndt | visual
  "document": { "title": "...", "date": "1974-05", "reference": "..." } | null,   // for basis == drawing; the drawing itself is an attachment (7.3)
  "bars": [
    { "spec": "BSt III", "diameter_mm": 8,
      "points": [[x,y,z], ...] }                        // open centreline polyline, in the stored coordinates of position.snapshot_id
  ]
}
// summary: {rebar_diameter, range: [min, max] over bars, mm, claimed (drawing) | measured (scan, exposed)}
// steel grade into the fold, if wanted: a separate `rebar_spec` claim sharing the attachment (7.1 fan-out)
```

One record per source: a drawing, a scan survey, one exposure. Viewers draw the bars on the
snapshot named by `position.snapshot_id`; a new snapshot (new coordinates) needs a new layout record. GH: the
`ReinforcementLayout` builder (curves + spec + diameter) posted by the generic `AddEvidence`
component --- the one evidence path in the 0.6 bridge.

---

## Appendix B --- Proxy primitives

All placements: right-handed, origin at the primitive centroid, `z` along the primitive's
principal (extrusion / axis) direction, coordinates in mm in the snapshot's stored geometry
coordinates (the coordinates named by `capture`, section 3.2.3; never transformed).

| primitive | `params` | faces (`face_id`) | UV per face |
|---|---|---|---|
| `box` | `{ "size": [sx, sy, sz] }` | `+x -x +y -y +z -z` | orthographic on the face plane, u/v along the two in-plane axes |
| `prism` | `{ "profile": [[x,y],...], "holes": [[[x,y],...]] \| null, "height": h }` | `top`, `bottom`, `side_<k>` for k in 0..n-1 (edge k of profile) | caps: orthographic in xy; side k: u along edge k, v along z |
| `cylinder` | `{ "radius": r, "height": h }` | `top`, `bottom`, `lateral` | caps: polar (r, theta); lateral: (theta, z) unrolled |
| `hull` | `{ "vertices": [[x,y,z],...], "faces": [[i,j,k],...] }` | `sphere` (single) | (theta, phi) from centroid; value = concavity depth along the ray, always >= 0 |

Deviation channels: `distance` (signed mm, positive outward), `normal_deviation` (degrees),
`occupancy` (point count, saturating). 16-bit PNG, three channels, with `scale_mm` / `offset_mm`
per map for `distance`.

Proxy placements follow the primitive (z = extrusion / axis direction) and are **independent of
the snapshot's `frame`** (section 4.3 stage 1, decision 7.10), which keeps its own axis convention --- a
beam's prism has z along the beam, its `frame` has x along the beam.

---

## Sources

- Regulation (EU) 2024/3110 of 27 November 2024 laying down harmonised rules for the marketing of
  construction products (Construction Products Regulation, recast) ---
  <https://eur-lex.europa.eu/eli/reg/2024/3110/oj/eng> (PDF copy: `reference/pdf/CPR_2024_3110.pdf`). Cited: Arts 3, 14, 15, 18, 21, 22, 26, 75--80; Annexes I, II, IV, V, VII; Recitals 34--36, 91--92.
- Regulation (EU) 2024/1781 (Ecodesign for Sustainable Products, ESPR) --- Arts 9--15, Annex III;
  Arts 12--14 on unique identifiers, DPP registry and web portal, applied to construction products
  via CPR Art 79 --- <https://eur-lex.europa.eu/eli/reg/2024/1781/oj/eng>.
- CEN-CENELEC, *Digital Product Passport, the cornerstone for the implementation of sustainability
  and circularity on the European Single Market* (15 Jul 2026) --- the EN 18216/18219/18220/18221/
  18222/18223/18239/18246 family, JTC 24, request M/604 ---
  <https://www.cencenelec.eu/news-events/news/2026/en-in-the-spotlight/2026-07-15-dpp/>;
  Commission Implementing Decision (EU) 2026/1736 (OJ 15 Jul 2026) citing six of them.
- CIRPASS-2 (Digital Europe Programme, 2024--2027), construction lighthouse pilot led by Cobuilder ---
  <https://cirpass2.eu/>, <https://cobuilder.com/en/digital-product-passport-dpp/eu-funded-project-digital-product-passports/>.
- Directive (EU) 2024/1275 (EPBD recast) --- renovation passports (Annex VIII), digital building
  logbooks, whole-life carbon --- <https://eur-lex.europa.eu/eli/dir/2024/1275/oj/eng>.
- EN 15804:2012+A2:2019 --- core rules for EPDs of construction products; its 13+6 indicators are
  CPR Annex II. Level(s) framework (EC JRC), indicators 1.2, 2.1, 2.4.
- Regulation (EU) 2023/1542 (batteries) --- the first mandatory DPP (Feb 2027), reference
  implementation only.
- Directive 2008/98/EC (Waste Framework Directive) --- end-of-waste, referenced by CPR Art 3(20)/(25).
- M. Bernhard, *HYBREP: A Hybrid Representation Framework for Computational Design with Reclaimed
  Building Elements*, DBT ETH Zuerich --- `reference/pdf/Bernhard_HYBREP.pdf`.
- NBS Uniclass 2015, Materials table (Ma) v1.1, July 2026 --- <https://uniclass.thenbs.com/taxon/ma>
  (codes checked 2026-09-23).
- Commission Decision 2000/532/EC (List of Waste) as amended by Decision 2014/955/EU, chapter 17;
  verified 2026-09-28 against its verbatim German transposition, Abfallverzeichnis-Verordnung
  (AVV), Anlage --- <https://www.gesetze-im-internet.de/avv/anlage.html>.
- EN 12504-2:2021, EN 12504-1:2019, EN 12390-3:2019, EN 13791; ASTM C805, C42/C42M, C39/C39M ---
  see `MEASUREMENTS_SPEC.md` section 3 and its source list.
- W3C/OGC SOSA/SSN (`sosa:Observation`, `sosa:Sampling`, `phenomenonTime` / `resultTime`) and
  W3C PROV-O --- the shape of the evidence envelope (section 3.3).
- DIN SPEC 91484:2023-09 --- recording of reusable building products (pre-demolition audit); to be
  cross-checked against section 3.1 and section 10.3 once obtained.
