# Spherical harmonics descriptor --- source check 2026-10-08

A student's repository `00_Trajectory_Vault_Reuse` (reuse vault from debris stones, Grasshopper
pipeline) contains a spherical harmonics (SH) shape descriptor. The author has agreed that CSC
reads the repository and integrates the SH descriptor (decision 8.126). The repository URL and the
author's contact are kept in untracked notes (8.27). The repository has no licence file yet (state
of 2026-10-08, last commit 2026-09-27); the maintainer asks the author to add a permissive one (MIT,
Apache-2.0 or similar). Code is copied only after that licence is committed.

Findings below; the open topics they raise are O19--O25 in `DESIGN_DECISIONS.md`.

## Where the code is

One file: `00_concept/gh_pipeline/00_matchmaking/M4_SHGoal.py` (about 200 lines), a Grasshopper
Python 3 component in the matchmaking chain (`M0` loader ... `M7` Hungarian assignment, `M9`
orientation). It emits one JSON goal block per mesh, which `M5_Collector` gathers and
`M6_CompatibilitySolver` turns into a cost matrix. No other file in the repository uses SH.

## What it computes

1. **Sampling:** `n_rays` (default 256) approximately uniform directions on a Fibonacci lattice.
2. **Radial function:** from the volume centroid (`VolumeMassProperties`) one ray per direction;
   the first hit distance (`Intersection.MeshRay`); a miss gives 0.
3. **Scale:** all distances divided by the largest one --- the descriptor is scale-invariant.
4. **Projection:** real SH up to degree `degree` (default L = 4), associated Legendre functions
   from `scipy.special.lpmv`; each coefficient is the mean over the rays of distance x basis
   function.
5. **Invariance about Z:** per degree l the signed zonal coefficient a_l0 and, for each m > 0, the
   amplitude `hypot(a_l,m, a_l,-m)`. These do not change under a rotation about Z and do change
   under a tilt. Length sum_{l=0..L} (l + 1) = 15 for L = 4.
6. **Yaw hint:** the phase `atan2(a_l,-1, a_l,1)` of the strongest m = 1 band, with a validity flag
   (amplitude > 1e-3). It goes to the orientation optimiser `M9`, not into the cost vector.
7. **Output block:** `{"feature": "sh_spectrum", "type": "vector", "value": [...], "constraint",
   "weight", "meta": {n_rays, degree, sampling: "fibonacci", frame: "yaw_about_z", yaw, yaw_valid}}`.
8. **Comparison** (in `M6`): L2 distance between two spectra divided by the largest L2 in the
   matrix.

## Portability

- The maths is pure numpy / scipy: `fibonacci_directions`, `sh_real`, `encode_z_invariant`
  (lines 54--104). Reusable almost unchanged.
- Rhino-bound: only `raycast_distances` (`MeshRay`, `VolumeMassProperties`). Needs a server-side
  raycaster on the snapshot source (mesh; point clouds have no surface to hit).
- Grasshopper scaffolding to drop: `sc.sticky` cache with a coarse `mesh_hash` key, DataTree
  handling. The runner's stage stamps and result cache (8.46, 8.122) replace it.

## Caveats

- **Assumes Z is the true vertical.** Fits stones lying in a vault; CSC snapshots have no such
  axis. Options: full rotation invariance (energy per degree, sqrt(sum_m a_lm^2)) or computing in
  the stage-1 `frame` (7.10), which inherits the frame's ambiguity for symmetric pieces (same
  problem as the radial signature, `FUTURE.md`).
- **Star-shaped assumption.** First hit from the centroid is correct only when every surface point
  is visible from the centroid. Concave, hollow or L / U shaped parts, and parts whose centroid
  lies outside the solid, give a wrong descriptor without warning. Open or non-watertight meshes
  make `VolumeMassProperties` fail (falls back to the origin).
- **Scale is discarded** (normalised by the maximum distance); size must come from other
  descriptors (frame / `bbx`).
- **Quadrature constant:** the mean (1/N) is used where 4 pi / N would give true SH coefficients.
  The factor is the same for every piece, so comparisons are unaffected, but values are not
  textbook coefficients; the spec must say which convention is stored.
- **Sampling:** 256 rays suffice for L = 4; higher degrees need more rays (at least the
  (L + 1)^2 coefficients, in practice several times that).

## Candidate: inside and outside crossings (user idea, 2026-10-08)

Cast once from the inside, once "from the outside" (from a minimal enclosing sphere back toward the
part), and use both values. Notes for grilling O21 / O23:

- **One cast suffices.** If the outside rays lie on the line through the origin and point back to
  it, the outside first hit is the last crossing of the inside ray. One multi-hit ray per direction
  (e.g. trimesh `intersects_location(..., multiple_hits=True)`) gives `r_in` (first crossing, what
  the source uses) and `r_out` (last crossing, outer envelope). The sphere only fixes where outside
  rays start; aiming them at its own centre instead would put the two functions on different
  origins.
- **What it adds.** For star-shaped parts `r_in = r_out`. The gap `r_out - r_in` shows per direction
  where the part is concave or hollow, so the star-shaped assumption becomes measurable instead of
  silently wrong.
- **Point clouds** need no surface: nearest and farthest point inside a small cone around each
  direction give `r_in` and `r_out` directly.
- **Store two spectra, not one merged value:** `r_out` (robust outer shape) and the gap
  (concavity); equivalent to storing `r_in` and `r_out`. A single value (e.g. the mean) confuses
  "large and concave" with "smaller and convex". Length doubles (30 values for L = 4); casting
  cost barely changes.
- **Limits.** First and last crossing miss what lies between; a pipe and a solid rod can agree
  along some directions. Optional third function: material length along the ray (sum of inside
  intervals). The general form is the shell-based SH descriptor (Kazhdan, Funkhouser, Rusinkiewicz
  2003): concentric shells of the solid's indicator function, SH energy per shell, a radius x
  degree grid; handles any shape but needs a watertight solid or a voxelisation.
- **Origin.** With all crossings recorded, a centroid outside the solid (L / U parts) is harmless,
  but the descriptor still depends on the origin; the centre of the enclosing sphere or of the
  stage-1 `frame` box are steadier.
- **Overlap** with the hull concavity map (3.3) and HKS (8.6), which already serve `irregular`
  pieces; grilling decides whether the gap spectrum adds enough.

## Research pass (O25)

Before grilling O20--O24, search the literature again and record the findings here:
rotation-invariant SH descriptors and their shell decomposition, ray-based and extent descriptors
(Vranic), multi-hit and thickness variants, SH on point clouds, recent learned alternatives, and
how each compares with the stored radial signature and HKS.
