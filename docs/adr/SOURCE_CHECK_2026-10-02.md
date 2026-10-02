# Source check against the full texts --- 2026-10-02

Read from `reference/pdf/` (TU Darmstadt licences; PDFs stay untracked). Findings not yet worked
into `DATA_MODEL_SPEC.md`; each becomes a spec fix or an open topic to grill.

## Confirmed

- EN 12504-2:2021: >= 9 valid readings; impacts >= 25 mm apart and from edges; median as whole
  number; set discarded if > 20 % of readings deviate > 25 % from the median; direction
  adjustment per manufacturer. Replaces EN 12504-2:2012.
- EN 12504-1:2019 + AC:2020 (DIN EN 12504-1:2021-02): 2:1 class = 1.95--2.05; f = F / A from the
  mean diameter, 0.1 MPa.
- EN 12390-3:2019: loading rate 0.6 +- 0.2 MPa/s; satisfactory / unsatisfactory failure
  patterns.
- EN 15804+A2 (+AC:2021): 13 core + 6 additional indicators = CPR Annex II (a)--(s).
- CPR Art 75(2)(i): 25 years after the last product of the type --- from the CPR, not EN 18221.
- ISO/IEC 15459: identities need a registered issuing agency (15459-2); a UUID is not one.

## Spec corrections (fix in A.1 / A.2 / 10.x)

1. **A.1 anvil check** (12504-2, 7.1.2 / 7.3): five readings on the reference anvil *before and
   after* the test series, each within +-3 of the manufacturer value; 2021 recommends a second,
   softer anvil. The payload holds one `anvil_check`; needs `before` / `after` (+ optional second
   anvil).
2. **A.1 test location** (12504-2, 6.1): members >= 100 mm thick and firmly fixed; smaller pieces
   only if firmly supported --- relevant for loose reclaimed pieces. Add `member_thickness_mm`,
   `support` (fixed in structure / clamped / loose). Area ~300 x 300 mm. Hammer use 0--50 deg C.
   Readings that crush a near-surface void are discarded (reason for `rejected_reading_indices`).
3. **A.1 / A.2 report items**: "deviations from the standard" (free text) and the responsible
   person's declaration are mandatory report items in all three standards --> `deviations` field;
   the declaration maps to `performed_by` + verification.
4. **A.2 reinforcement** (12504-1, 6.3; EN 13791, 6(5)--(6)): a core with a bar in or near its
   axis is rejected and redrilled --- not a UI warning; a transverse bar is recorded with diameter
   and position in mm and assessed separately. Replace `reinforcement_present` by
   `reinforcement[] {orientation: transverse | longitudinal, diameter_mm, position_mm}`;
   longitudinal --> invalid for strength.
5. **A.2 missing fields**: estimated maximum aggregate size (mandatory report item; d / Dmax < 3
   biases strength); 1:1 class = 0.90--1.10; storage = sealed container or water (>= 48 h,
   20 +- 2 deg C) --- `air_dried` is not a 2019 condition; failure code = letter of the most
   similar unsatisfactory pattern (EN 12390-3 Fig 2 / 4).
6. **A.2 result / EN 13791:2019**: f_c,is is the 2:1-core equivalent; 1:1 cores x CLF 0.82
   (normal concrete). Diameter >= 75 mm (>= 50 mm only if impractical; then 1:1 and 3 cores per
   location). **German NA (DIN EN 13791/A20:2022-04, NA.7):** 1:1 core 50--150 mm = water-stored
   150 mm cube; 2:1 core 75--150 mm = 150 x 300 cylinder --- keeps `fc_is_cube_mpa` meaningful in
   Germany. `conversion_basis` should name EN 13791 + A20.
7. **Rebound --> strength** (EN 13791, 8.2; A20, NA.8.5): a site correlation needs >= 8 (better
   10) rebound/core pairs at the same locations, extrapolation <= 4 MPa, and a location estimate is
   the lower 5 % prediction bound, not the curve value. Without cores, Germany allows only a
   **strength class** from the median R / Q (A20 Tables NA.6 / NA.7, per location and per test
   region), N-type hammer; not if carbonation > 5 mm (unless ground off), not on fire / frost /
   chemically attacked surfaces; Q needs a carbonation time factor. --> `derived[]` model kinds
   `en13791_correlation`, `din_a20_na6` / `na7` (quantity `concrete_class`); carbonation rule in
   validation.
8. **10.6, EN 18221 row**: 18221 does not set 25 years. It requires every change of a passport to
   be archived, point-in-time retrieval for authorised actors, a backup service provider, OAIS
   (ISO 14721) as guidance. EN 18222 has `ReadDPPVersionByIdAndDate`.
9. **10.2**: "data carrier per ISO/IEC 15459" --> carriers are EN 18220; identifiers must follow
   one of the five EN 18219 schemes.
10. **2.5**: cover meter --> cite prEN 12504-5:2023 (draft, electromagnetic covermeters) instead of
    BS 1881-204; also the basis for `reinforcement_layout` with `basis: scan`.

## New open topics (to log as O13--O16 and grill)

- **O13 Identifier scheme (EN 18219).** Five schemes; two need no issuing agency: **did:web**
  (scheme 3, "lightweight, non-DLT", W3C DID 1.0) and **DOI** (scheme 5, ISO 26324; TU Darmstadt
  can mint DOIs). A raw UUID on the tag is none of them (EN 18220 5.2.1: the carrier encodes an
  EN 18219 identifier). Revisit 6.9 / the deferred `identifiers[]`?
- **O14 History of identity edits (EN 18221 4.2; DIN SPEC 91484 Table 6 "versioning").**
  Snapshots are versioned, identity metadata PATCHes are not (decision 1.8: no audit
  subsystem). History cannot be reconstructed later --- by the 6.8 rule this is 0.6 work.
- **O15 EN 13791 test regions and paired locations.** A characteristic in-situ strength is per
  test region (several similar members of one concrete) and correlations need rebound and core
  at the *same* location. CSC has no test-region grouping (7.2 dropped campaigns) and no link
  between a rebound record and the core taken at its spot.
- **O16 DIN SPEC 91484 gaps.** Stage 1 / 2 "shall" fields CSC lacks: connection type and
  dismantlability (DGNB Building Resource Passport), location within the source building,
  construction method (monolithic / prefabricated / mixed), reuse-potential verdict (yes / no /
  undecided + reason), manufacturer, suspected pollutants; documentation kinds (CE / Ue marking,
  type plate, DoP) for `archival_document`. Tool requirements: PDF summary export, completeness
  indicator. Which are 0.6 (breaking) vs. deferred (additive)?

## Not yet read

prEN 12504-5 beyond its structure; EN 18222 in detail; ESPR, WFD, Decision 2026/1736 (not in
`reference/pdf/`).
