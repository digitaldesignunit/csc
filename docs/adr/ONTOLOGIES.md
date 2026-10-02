# Ontologies and CSC --- CERO check (2026-10-02)

Question: are existing ontologies useful for CSC, and should CSC comply with or translate into
the Concrete Element Reuse Ontology (CERO, `https://w3id.org/cero`, repository
`RUB-Informatik-im-Bauwesen/crc1683-ontologies`, Chair of Computing in Engineering, Ruhr
University Bochum, CC BY 4.0)? Open topic O18.

**Decided (8.39, 8.44, 2026-10-02):** translate, never adopt. A JSON-LD view and a CERO exporter
read mapping columns on the vocabulary rows; four CERO-listed quantities become rows
(`exposure_class`, `chloride_content`, `elastic_modulus`, `crack_width`); exports land in P10
(0.6.1, after cutover). Spec section 7.8.

## What CERO is (version 0.1, repository last changed 2026-01-28)

- A **property dictionary** in the ISO 23386 style (`isoprops`): 53 properties, each with a
  GUID, label, data type, unit (QUDT), group and version, sorted into groups (identification;
  mechanical properties; geometry and damage; durability and remaining service life; physical
  and material; process and lifecycle; sustainability). The ontology description reads "To be
  defined"; the three sibling ontologies (COPO for deconstruction projects after DIN 18007, LCAO
  for LCA after PEF 3.1, LCMO for life-cycle modules) carry "TODO" descriptions.
- Every property is also an `owl:DatatypeProperty` with domain `bot:Element` (W3C Building
  Topology Ontology): **one literal value hangs directly on the element.** No time, no source,
  no method, no confidence, no range; the unit sits on the property definition, not the value.
- Many properties are strings (`connectionType`, `reinforcementRatio`, `chlorideContent`,
  `loadBearingCapacity`); no value lists; `sh:` (SHACL) is declared but no shapes exist.
- Overlaps: `compressiveStrength` / `concreteCompressiveStrength`, `reinforcementTensileStrength`
  / `reinforcingSteelTensileStrength`, `youngModulus` / `concreteStiffness`.
- Concrete elements only; includes process and LCA figures (transport distance, energy, working
  hours, machine and material resources) that CSC does not model.

## Mapping CERO --> CSC

| CERO | CSC | fit |
|---|---|---|
| `identifier` | `_id`, `catalog_number` | yes |
| `elementType`, `initialFunction` | `original_function` (IFC class name); `origin.construction_work.use` | yes (CERO free text) |
| `initialProject`, `origin`, `location` | `origin.construction_work`, `origin.place`; current `snapshot.location` | yes (CERO one string each) |
| `length`, `width`, `height`, `diameter`, `crossSection`, `elementDimensions`, `volume` | `bbx`, proxy params (derived) | yes, derived |
| `shapeCategory` | `shape_class` | yes |
| `weight`, `density` | quantities `mass`, `density` | yes |
| `color`, `photo` | snapshot `color`, photos | yes |
| `compressiveStrength`, `concreteCompressiveStrength` | `compressive_strength`, `compressive_strength_in_situ` | yes, as a folded range |
| `concreteCover` | `cover_depth` | yes |
| `carbonationDepth` | `carbonation_depth` | yes |
| `reinforcementLayout` | `reinforcement_layout` evidence (A.4) | yes (CERO a string) |
| `cracks`, `crackWidth`, `damageClass`, `extraordinaryDamage`, `internalDefects` | `cracking`, `spalling`, `corrosion` severities, `condition_grade` | partly (no crack width) |
| `chlorideContent`, `youngModulus`, `concreteStiffness`, `reinforcementRatio`, `reinforcementMass`, `reinforcementTensileStrength`, `reinforcementYoungModulus` | --- | missing quantities (additive rows, 6.8) |
| `exposureClass`, `loadHistory`, `loadBearingCapacity`, `remainingServiceLife`, `toxicSubstances` | --- (`service_life`, hazardous evidence deferred) | missing |
| `connectionType`, `anchorPoints`, `accessibility` | --- | missing; same gap as DIN SPEC 91484 (O16) |
| `finishing`, `dceClassification` | --- | missing |
| `transportDistance`, `energyConsumed`, `workingHours`, `machineResources`, `materialResources`, `environmentalImpact`, `environmentalActions` | --- | out of scope (process / LCA data; `processes` removed, 6.13) |

## Assessment

**Comply: no.** CERO's model is one value per property on the element. CSC's is evidence ---
who measured what, when, by which method, verified by whom --- folded into a range with
confidence and source (decisions 1.x, 2.x). Adopting CERO as the model would discard exactly
what makes a CSC record usable as justification for reuse. CERO is also v0.1, concrete-only
and undocumented.

**Translate: yes, later, one way, as an export.** CSC --> CERO is lossy but simple: each folded
property becomes one CERO value (the conservative bound, as the CPR projection in section 10.3),
identity and origin fields map directly, and the provenance stays behind a link to the CSC
record. CERO --> CSC import would land as `claimed` evidence of unknown source.

**How ontologies are useful to CSC in general:**

1. **At the boundary, never as storage.** MongoDB + Pydantic stay the source of truth: the
   lifecycle, permission, freeze and fold rules are code, which no ontology carries. A JSON-LD
   view of the existing JSON (`@context` mapping keys to IRIs) costs little and makes every
   record a linked-data document without an RDF store.
2. **As naming and unit authority.** A mapping column per vocabulary row (as Uniclass already
   is for materials): quantity --> QUDT / UCUM unit, bSDD / IFC property, CERO property;
   `original_function` --> IFC; identity --> `bot:Element`, `construction_work` -->
   `bot:Building`. Stable IRIs make CSC data citable and joinable.
3. **The ontologies that carry weight for CSC:** SOSA/SSN and PROV-O (already the evidence
   shape), BOT, QUDT, IFC / bSDD --- the likeliest base of the construction-product data
   dictionary the CPR delegated act will name (CIRPASS-2, section 10.6) --- and EN 18223 (DPP
   interoperability) once relevant. CERO is a neighbouring research vocabulary, not a standard.
4. **As a checklist.** CERO's list surfaces what reuse researchers expect on a concrete element:
   connection type and anchor points (also DIN SPEC 91484), exposure class, chloride content,
   elastic modulus, rebar ratio / grade / strength, load history, remaining service life. These
   are candidate quantity rows, mostly additive.
5. **As a collaboration channel.** CERO lacks provenance and time; CSC's evidence envelope
   (SOSA + PROV) is a contribution the CERO authors could adopt, and a shared mapping would let
   both catalogues exchange elements. That is the user's call.
