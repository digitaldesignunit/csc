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
- ESPR 2024/1781: Art 13(1) registry "by 19 July 2026"; Art 14 public web portal; Art 10(1)(c) +
  Annex III second paragraph: data carrier **and** unique product identifier comply with
  ISO/IEC 15459-1 to -6 "until the references of harmonised standards are published" --- since
  Decision 2026/1736 that is EN 18219 / EN 18220. Art 12(4)(b): a delegated act will set rules
  for operators creating their own identifiers without an issuing agency. Art 10(1)(e):
  customer personal data only with explicit consent (GDPR Art 6).
- WFD 2008/98/EC (2008 text, not consolidated): Art 3(13) re-use = products "that are not waste"
  used again for the same purpose; Art 5 by-product conditions; Art 6 end-of-waste conditions.
  The 2018/851 amendments are not in the file; the readings in spec 2.8 hold for the 2008 text.
- EPBD 2024/1275: Art 2(41) digital building logbook; Art 12 renovation passports "by 29 May
  2026" on the Annex VIII framework; Art 7 life-cycle GWP disclosure from 2028 / 2030.
- `reference/pdf/` file notes: `EU_2000_532_EC*.pdf` are copies of the WFD (same checksum), so
  the List of Waste itself is not there (its codes were verified against the AVV on 2026-09-28);
  `EU_2024_679*.pdf` is the GDPR, Regulation (EU) **2016**/679; Decision 2026/1736 (added later) read in
  full: adopted 14 July 2026, OJ 15.7.2026, in force on publication; Annex lists EN 18216, 18219,
  18220, 18221, 18222, 18223 (all :2026); presumption of conformity with ESPR Arts 10 and 11 via
  ESPR Art 41(2).

## Spec corrections (fix in A.1 / A.2 / 10.x)

Items 1--7 and 11 are worked into Appendix A by decision 8.41; items 8--10 were fixed on
2026-10-02.

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
9. **10.2**: ESPR Annex III names ISO/IEC 15459 for identifier and carrier only until harmonised
   standards are cited; since 2026/1736 the presumption runs through EN 18219 (five identifier
   schemes, two without issuing agency) and EN 18220 (the carrier encodes an EN 18219 identifier).
10. **2.5**: cover meter --> cite prEN 12504-5:2023 (draft, electromagnetic covermeters) instead of
    BS 1881-204; also the basis for `reinforcement_layout` with `basis: scan`.
11. **A.4 `basis: scan`** (prEN 12504-5, 7.2): report items are covermeter make / type and last
    calibration, site calibration, measured covers, bar size *assumed or known*, estimated
    accuracy (under ideal conditions better than 20 % for size and cover when neither is known),
    bar spacing. A.4 has none of these: add `instrument`, `diameter_known: bool`, `cover_mm` per
    bar, `accuracy_note`.

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

## Coverage

Read in full or in the relevant clauses: EN 12504-1, -2, prEN 12504-5, EN 12390-3, EN 13791 +
A20, EN 15804, EN 18219--18222, ISO/IEC 15459-1..6, DIN SPEC 91484, CPR, ESPR, WFD, EPBD.
GDPR not re-read (Arts 6 and 17 are cited only by number). EN 18222: every passport holder
must offer `ReadDPPById`, `ReadDPPByProductId`, `ReadDPPIdsByProductIds`; version-by-date reads
are "should" --- relevant only once the deferred passport export is built.
