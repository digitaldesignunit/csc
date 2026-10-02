# CSC 0.6 --- regulations and standards

What the CSC 0.6 data model (`DATA_MODEL_SPEC.md`) follows, aligns with or prepares for. Status
2026-10-02. Written to be copied into project documents.

**Reading the levels.** *Implemented* --- the software enforces it. *Aligned* --- fields and rules
are designed after the text and map onto it, but CSC is not itself subject to it or certified
against it. *Prepared* --- the model leaves room; the work is deferred. CSC is a research
catalogue of reclaimed building components, not a construction-product Digital Product Passport
system: the CPR passport obligations start only with a delegated act under CPR Art 75(1), which
does not exist yet.

## EU law

| Act | What CSC does | Level |
|---|---|---|
| **Regulation (EU) 2016/679 (GDPR)** | Personal data of performers (name, email, ORCID) is shown to signed-in users only; anonymous readers see the organisation. Email never appears in lists. Redaction of a person across all records (Art 17). Photo uploads are stripped of GPS position, owner and camera serial number. Attachments are downloadable only when signed in. | Implemented (photo stripping, access rules); redaction in 0.6 |
| **Regulation (EU) 2024/3110 (Construction Products Regulation, recast)** | Record fields carry a mapping to the Digital Product Passport content (Annex V): identity and serial number, main materials (Annex IV 1.2(e)), date and place of the latest deinstallation (Annex V 1(h), Art 18(2)(a)), declared performances per essential characteristic. Life cycle of a used product starts at the latest deinstallation (Art 3(53)). System requirements: persistent identifiers, open machine-readable formats (Art 77(1)(d)), tiered access (Art 75(2)(c)), no end-user personal data without consent (Art 77(1)(e)), retention --- nothing published is ever hard-deleted, withdrawn records stay as tombstones (Art 75(2)(i), 78(h)). | Aligned |
| **Regulation (EU) 2024/1781 (Ecodesign for Sustainable Products, ESPR)** | Framework the CPR passport uses for unique identifiers, registry and web portal (Arts 12--14, applied via CPR Art 79). CSC resolves every piece through a persistent URL (`/id/{uuid}`, QR / NFC tags carry the raw UUID). | Aligned; standardised identifiers prepared |
| **Directive 2008/98/EC (Waste Framework Directive)** | How a piece entered circulation is recorded by kind --- deinstallation, demolition, production offcut, surplus --- because only a deinstalled piece is a CPR used-product candidate, demolition output is waste until end-of-waste (Art 6), and an offcut is a by-product question (Art 5). | Aligned; end-of-waste basis prepared |
| **Commission Decision 2000/532/EC (List of Waste), as amended by 2014/955/EU, chapter 17** | Every material carries its waste-code class (e.g. concrete 17 01 01), derived from the material and overridable; hazardous codes are never assigned without evidence. Codes verified against the German transposition (AVV, Anlage). | Implemented in 0.6 |
| **Directive (EU) 2024/1275 (EPBD recast)** | The construction work a piece left or went into carries an identifier slot for a digital building logbook or cadastral id. | Prepared |

## Harmonised and European standards

| Standard | What CSC does | Level |
|---|---|---|
| **EN 18219, EN 18220, EN 18221, EN 18222 (Digital Product Passport: unique identifiers, data carriers, data storage and persistence, APIs)** --- cited in the OJ by Implementing Decision (EU) 2026/1736 | Design targets for the identifier slot, the QR payload, retention and the export API. | Prepared (deferred until a passport export is needed) |
| **EN 18246 (DPP data authentication, reliability, integrity)** --- not yet cited | Content hashes on every record (`etag`, attachment `sha256`), corrections by superseding records instead of edits. | Aligned with the principle |
| **EN 15804+A2 (EPD core rules)** | Its 13 core + 6 additional indicators equal CPR Annex II; environmental quantities are to carry its indicator codes. | Prepared |
| **EN 12504-2:2021 (rebound number)**; ASTM C805 later, as an additional method | Rebound tests store every reading, the impact direction, hammer type and calibration; the server recomputes the median and the discard rule. A rebound number is never stored as a strength. | Implemented in 0.6 (evidence, phase P6) |
| **EN 12504-1:2019 (cored specimens)**, **EN 12390-3:2019 (compressive strength)**, machine per **EN 12390-4**; ASTM C42, C39 later, as additional methods | Core tests record sampling, specimen preparation and testing separately, with both dates; the server recomputes F / A and the length-to-diameter class. | Implemented in 0.6 (P6) |
| **EN 13791:2019 (in-situ compressive strength assessment)** with the German national annex **DIN EN 13791/A20:2022-04** | Strengths derived from rebound or cores are stored as derived results naming their conversion model, separate from measured values. | Implemented in 0.6 (P6) |
| **ISO/IEC 17025 (testing laboratories)** | A result can be marked *accredited* only if a performing lab carries an accreditation whose scope covers the test standard, valid at the test date. | Implemented in 0.6 (P6) |
| **DIN SPEC 91484:2023 (recording reusable building products, pre-demolition audit)** | National reference for the record of a reusable product. Cross-checked 2026-10-02: dimensions, quantity, photos, condition, function, construction year, production year, documents, expert reports, JSON exchange, access control and mobile use are covered; connection type, dismantlability (DGNB classes), location within the source building, construction method and manufacturer are added in 0.6 (decision 8.38); the human-readable PDF summary of section 8 follows in 0.6.1 (8.44); a reuse verdict and a pollutant record are postponed. | Aligned (0.6), partly postponed |
| **DGNB Building Resource Passport v1.3** | Detachability and material separability classes and connection words are taken from it. | Implemented in 0.6 (vocabulary) |

## Data and interoperability standards

| Standard | What CSC does |
|---|---|
| **IFC 4.3 (ISO 16739-1), buildingSMART** | A piece's original function uses IFC element class names (`IfcBeam`, `IfcSlab`, ...); simplified geometries map to IFC solid types. |
| **UCUM** | Units of every quantity are UCUM codes; the server converts to a canonical unit. |
| **ISO 8601** | All timestamps, with an explicit precision (exact, day, month, year, unknown). |
| **W3C/OGC SOSA/SSN and W3C PROV-O** | The evidence record follows their shape: the component is the feature of interest, a core is a sample, every result names who performed it, who recorded it, and when. |
| **ORCID, ROR** | Optional identifiers for persons and institutions in every attribution. |
| **JSON Schema** | Every record type is published as a JSON Schema by the API. |
| **Uniclass 2015, Materials table (Ma)** | Secondary material code where a current one exists. |
| **Level(s) (EU framework for sustainable buildings)** | Catalogue data is input for indicators 2.1 (bill of materials) and 2.4 (design for deconstruction). |

## Research basis

- M. Bernhard, *HYBREP: A Hybrid Representation Framework for Computational Design with Reclaimed
  Building Elements* (ETH Zuerich): simplified shapes that keep their deviation from the scan,
  properties as ranges with confidence and source.
