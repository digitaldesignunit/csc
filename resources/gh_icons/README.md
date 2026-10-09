# Grasshopper Icons

This folder is the source-of-truth for **CSC (Catalog of Second Chances) Grasshopper component icons**. Icons are authored as **SVG** so LLMs can read and edit them as text, then exported to **24×24 PNG** for Grasshopper.

Each component gets:

1. An **SVG source file** -> the canonical, LLM-editable artwork (text in git, diffable, tweakable in chat)
2. A **24×24 PNG export** -> rasterized from the SVG for Grasshopper UserObjects

**Why SVG first:** Grasshopper ultimately needs a 24×24 bitmap, but SVG is the working format. An LLM can read, edit, and regenerate `.svg` files directly (paths, strokes, colours) without re-prompting an image model for every tweak.

---

## Folder layout

```
resources/gh_icons/
├── README.md                 ← this file (spec + component list + prompts)
├── svg/                      ← canonical source (edit these)
│   └── {NickName}.svg
└── 24x24/                    ← raster export for Grasshopper (generated from svg/)
    └── {NickName}.png
```

**Naming:** use the component `NickName` exactly as defined in source (e.g. `CSC_Session.svg`, `CreateComponentIdentity.svg`).

Icons are applied when exporting UserObjects via `ExportScriptsAndSource` (single shared icon path today) or by setting `IconOverride` on individual components -> both expect the **PNG** in `24x24/`.

---

## Grasshopper icon specification

Based on the [official Grasshopper icon guide](https://developer.rhino3d.com/en/guides/grasshopper/grasshopper-icons/) and the Grasshopper API (`GH_Component.Icon` expects **24×24 pixels**).

### SVG source (canonical)

| Property | Value |
| --- | --- |
| **Canvas** | `viewBox="0 0 24 24"`, `width="24"`, `height="24"` |
| **Format** | Plain **SVG** (XML), no embedded raster images |
| **Geometry** | `<path>`, `<line>`, `<rect>`, `<circle>`, `<polygon>` -> prefer paths for complex shapes |
| **Strokes** | Explicit `stroke` + `stroke-width` (typically 1–2 in 24×24 units); use `stroke-linecap="round"` / `stroke-linejoin="round"` where helpful |
| **Fills** | Solid fills only; avoid gradients, filters, and masks unless strictly necessary |
| **Safe content area** | Keep artwork inside **x/y 2–22** (~20×20 px, **2 px margin** on all sides) |
| **Background** | Transparent (no background `<rect>`) |
| **Structure** | Keep markup minimal and readable; optional `<g id="symbol">` / `<g id="shadow">` groups |
| **Colours** | Hex or named colours in attributes (`fill="#000000"`), not CSS classes -> easier for LLMs to edit |

Minimal SVG skeleton:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <g id="shadow" opacity="0.25"><!-- optional drop shadow --></g>
  <g id="symbol"><!-- icon artwork, inside 2–22 --></g>
</svg>
```

### PNG export (for Grasshopper)

| Property | Value |
| --- | --- |
| **Size** | **24 × 24 px** exactly |
| **Format** | **PNG**, 32-bit RGBA |
| **Source** | Rasterized from the matching `svg/{NickName}.svg` |
| **Drop shadow** (optional, recommended) | Blur 2 px · black · alpha 65/255 (~25%) · offset +1 px right, +1 px down -> implement in SVG or at export time |
| **Style** | Match native Grasshopper icons: clear line weights, high contrast, limited palette, simple geometric symbols, readable at canvas zoom |

### CSC visual identity (secondary)

Grasshopper icons should still read like Grasshopper icons first. Where it fits without hurting legibility at 24×24, you may use subtle CSC brand accents:

- Pink `#ef509c`
- Blue `#0000ff` / `#4080ff`

Prefer one accent colour per icon; avoid gradients and fine detail that disappear at 24×24.

### Checklists

**SVG source**

- [ ] `viewBox="0 0 24 24"` with artwork in the 2–22 safe area
- [ ] Vector paths only -> no embedded PNG/JPEG
- [ ] Transparent background
- [ ] Readable on light **and** dark Grasshopper canvas backgrounds
- [ ] No text labels (too small at 24×24)
- [ ] Valid XML (closed tags, escaped characters)

**PNG export**

- [ ] Rasterized from SVG at exactly 24×24 px
- [ ] Transparent background
- [ ] Drop shadow applied (if used on other CSC icons)
- [ ] Visually matches the SVG at canvas zoom

### Rasterizing SVG --> PNG

Regenerate `24x24/` whenever `svg/` changes. Examples:

```bash
# Inkscape (CLI)
inkscape svg/CSC_Session.svg --export-type=png --export-filename=24x24/CSC_Session.png -w 24 -h 24

# librsvg
rsvg-convert -w 24 -h 24 svg/CSC_Session.svg -o 24x24/CSC_Session.png
```

Use nearest-neighbour or a sharp downscale if exporting from a larger intermediate size.

---

## Generative AI workflow

Use this README as the prompt context when generating icons. **Output SVG source code**, then rasterize to PNG.

LLMs should prefer **writing/editing `.svg` files** over generating bitmaps -> the SVG can be iterated in chat (“ thicken the stroke”, “ swap accent to `#ef509c`”, “ move symbol 1px left”).

### Base prompt template (SVG)

```
Create a Grasshopper plug-in component icon as SVG for "{NickName}" ({SubCategory}).

Component purpose: {Description}

Requirements:
- Output complete SVG XML only (no markdown fence unless asked)
- viewBox="0 0 24 24", width="24", height="24"
- Transparent background, vector paths only (no embedded raster)
- Artwork inside x/y coordinates 2–22 (2px margin)
- Simple, bold, geometric style like native Grasshopper icons
- High contrast, 2–4 solid colours, no text, no photorealism
- Explicit fill/stroke attributes on elements
- Optional <g id="shadow"> with opacity ~0.25
- Optional CSC brand accent: pink #ef509c or blue #4080ff (one accent only)
- Icon metaphor should clearly suggest: {short visual metaphor}
```

### Base prompt template (image model fallback)

If using an image model, still end up with SVG: trace or redraw the result as paths in `svg/`, then export PNG. Do not treat a 1024×1024 PNG as the source of truth.

### Suggested visual metaphors (starting points)

Use these as hints for the `{short visual metaphor}` field->not literal labels.

| Area | Metaphor ideas |
| --- | --- |
| Session / auth | key, lock, user badge |
| Catalog fetch | cloud download, database, magnifier |
| Create / add | plus on box, upload arrow |
| Disassemble | exploded parts, tree branches |
| Transform | move/rotate arrows, insertion frame |
| Rhino sync | Rhino ↔ Grasshopper link, document refresh |
| PCA / geometry | axis triad, oriented bounding box |
| JSON tools | `{ }` braces, key/value |
| Embedding viz | scatter plot, coloured nodes |
| Development | wrench, package export |

After generation, save to `svg/{NickName}.svg`, validate in a browser or vector editor, then export `24x24/{NickName}.png`.

---

## Component catalog

Rescanned from `grasshopper_userobjects_src/` (Python + C# script components). Descriptions are shortened from each component's `Description` field for icon generation.

**Icon coverage:** every component below has `svg/{NickName}.svg` and a matching `24x24/{NickName}.png` (the P8 components got theirs on 2026-10-08; `ApplyFrame`, `FetchOriginalGeometry`, `ReinforcementLayout` and `GetComponentPassport` reuse the artwork of the names they replace).

| Icon | Meaning |
| --- | --- |
| yes | `svg/{NickName}.svg` exists (PNG export expected in `24x24/`) |
| **missing** | No SVG source yet --- needs artwork |

To verify PNG exports after SVG changes: `conda run -n csc python resources/gh_icons/rasterize.py --check`

### 0 Development

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `CSC_Update` | yes | Checks the server for newer CSC component sources/UserObjects and installs updates into the active Grasshopper document. |
| `CreatePublicDevelopmentFile` | yes | Saves a sanitized copy of the current GH definition: strips development-only components/groups and clears sensitive panel text for public sharing. |
| `CreateReleaseFiles` | yes | Saves a release-ready GH copy with development components removed to a target folder (optional fixed filename or timestamp). |
| `DefinitionDependencies` | yes | Lists all Grasshopper core and third-party plug-in libraries referenced by the open document, with names and versions. |
| `ExportScriptsAndSource` | yes | Scans the canvas for script components, deduplicates versions, and exports Python/C# source, `.ghuser` files, and pasteable XML. |
| `SaveAndSaveGHX` | yes | Saves the current definition as `.gh` and `.ghx`, plus timestamped archive copies; creates folders as needed. |

### 1 User

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `CSC_Session` | yes | Authenticates with the CSC API (server address input), keeps one connection alive, manages tokens, and caches identities, snapshots, and mesh PLY geometry in `scriptcontext.sticky`. |

### 2 Catalog Interface

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `AddComponentIdentity` | yes | POSTs a new component with its first state (a draft) from `CreateComponentIdentity` JSON, uploads the staged PLY files; the state stays a draft, submitted in the web (8.127); may consume a pending transmitted ID. |
| `AddComponentSnapshot` | yes | POSTs a new state of an existing component, or with `Supersedes` a correction, from `CreateComponentSnapshot` JSON; uploads the staged PLY files; the state stays a draft, submitted in the web (8.127). |
| `AddEvidence` | yes | POSTs evidence records (e.g. a `ReinforcementLayout`) with `/evidence/bulk`, all or none; always drafts, submitted in the web (8.127). |
| `FetchAllComponents` | yes | GET `/identities` --- fetches all identities joined with current snapshots as passport JSON `{identity, snapshots[]}`; cached. |
| `FetchAllSnapshots` | yes | Fetches passport JSON with every snapshot for one identity (`{identity, snapshots[]}`); input can be a UUID or passport JSON. |
| `FetchComponents` | yes | Fetches specific catalog components by identity ID; handles missing IDs; supports cache. |
| `FetchFilteredComponents` | yes | Server-side filtered catalog query (original function, material, dataset, complexity, dimensions, reservation status, shape class, material class, circulation). |
| `FetchOriginalGeometry` | yes | Fetches the original (as uploaded) snapshot geometry as binary PLY (ETag cache); falls back to reduced, then the inline preview; builds authored shapes. |
| `FetchReducedGeometry` | yes | Fetches the reduced snapshot geometry as binary PLY (ETag cache); falls back to the inline preview; builds authored shapes from their parameters. |
| `FetchSnapshot` | yes | Fetches passport JSON for one identity and a specific snapshot (`{identity, snapshots:[one]}`); input can be a UUID or passport JSON. |
| `FetchTransmittedID` | yes | Returns the pending transmitted component ID for the signed-in user from the backend. |
| `FilterComponents` | yes | Locally filters a list of passport JSON by original function, material, dataset, complexity, fragment, bounding-box size, shape class, and material class. |
| `ListIdentitySnapshots` | yes | Lists all snapshots for one identity (id and name); input can be a UUID or passport JSON. |

### 3 Component Operations

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `CreateComponentIdentity` | yes | Builds the `IdentityCreateBody` request for a new component (or a cut) from Rhino geometry and the builder objects; reduces and stages the mesh files. |
| `CreateComponentSnapshot` | yes | Builds the request for a new state (or a correction, `Supersedes`) of an existing component; reduces and stages the mesh files. |
| `CreateUUID` | yes | Generates and caches UUIDs; refresh input forces a new value. |
| `Actor` | yes | Builds one actor (person, organization, or account) as JSON for `Origin` or an evidence record. |
| `Origin` | yes | Builds how a component entered circulation (kind, date, place, construction work, who) as JSON. |
| `IdentityMetadata` | yes | Builds the identity fields of a new component (original function, material, trade name, origin ...) as JSON. |
| `SnapshotMetadata` | yes | Builds the fields of one recorded state (name, fragment, quantity, colour, location, notes, start date) as JSON. |
| `Capture` | yes | Builds how the geometry of a state was recorded (method, device, coordinate system, markers, fixtures) as JSON. |
| `ApplyFrame` | yes | Moves a component to its canonical orientation (longest side along X, centre at the origin) with the stored frame, or a frame computed locally. |
| `DisassembleComponent` | yes | Splits passport JSON `{identity, snapshots[]}` into Grasshopper-native outputs: metadata, condition, origin, capture, descriptors, frame, box, preview geometry. |
| `GetComponentPassport` | yes | Reads `csc_component` passport JSON from Rhino geometry objects. |
| `TransformComponent` | yes | Applies a Rhino transform to the client-side placement (`csc_placement`) of a snapshot in passport JSON. |

### 4 RhinoDoc Interaction

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `BakeComponents` | yes | Bakes passports into the Rhino document (meshes, point clouds, authored shapes, in the canonical orientation or at `csc_placement`) with a text tag per piece carrying the user text `csc_identity_id`, `csc_snapshot_id`, `csc_placement`, `csc_component`. |
| `SyncWithRhinoDoc` | yes | Reads the baked pieces back from the Rhino document by their tags and returns passports with `csc_placement` from where the tag is now. |

### 5 Matchmaking Tools

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `AssignmentPoints` | yes | Point-to-point assignment between design points and library points (greedy or Hungarian / SciPy). |

### 6 Data Tools

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `ComputePCA` | yes | Principal component analysis for dimensionality reduction on DataTree inputs. |
| `ComputeTSNE` | yes | t-SNE nonlinear embedding for visualization of high-dimensional data. |
| `ConvertGeoLocation` | yes | Parses a lat/lon string (e.g. from Google Maps) into numeric components and a vector. |
| `GetDescriptor` | yes | Reads one descriptor key from many passport JSON inputs or geometries; outputs a structured DataTree. |
| `JSONKeys` | yes | Lists JSON keys, types, and dot-notation paths up to a max depth. |
| `JSONGetValue` | yes | Extracts a value from JSON via dot-notation path (e.g. `descriptors.material.type`). |

### 7 Geometry Tools

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `ComputePCAOrientation` | yes | PCA-based orientation for meshes/breps/extrusions; returns OBB, aligned geometry, translation, and transform. |
| `ComputeFrame` | yes | Computes the frame of a piece offline with the server's rules (minimum-volume box, axes by extent, column stands). |
| `ReinforcementLayout` | yes | Builds a `reinforcement_layout` evidence record from bar centrelines, steel grades and diameters; post it with `AddEvidence`. |
| `ExtrusionProfile` | yes | Extracts the profile curves of a Rhino extrusion. |
| `FindLargestFlatSide` | yes | Finds the largest flat face cluster on a mesh (normal clustering + sampling heuristics for large meshes). |
| `MaxInscribedQuad` | yes | Maximum-area inscribed quadrilateral inside closed polylines (multi-start optimization). |
| `RadialSignature` | yes | Radial ray-cast shape signature for planar curves (distances + boundary tangents at intersections). |

### 8 Visualization

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `CreateArrangement` | yes | Lays out passport JSON components on a square grid from snapshot bounding boxes (spacing + insertion point). |
| `CurvePreviewLW` | yes | Custom curve preview with configurable line weights in the Grasshopper viewport. |
| `ViewCaptureToFile` | yes | Captures the active Rhino viewport to PNG with size, background, and grid/axis options. |
| `VisualizeEmbedding` | yes | Places geometry at PCA/t-SNE (or other) embedding coordinates; 1D–3D layout, extra dims mapped to RGB. |

### 9 D2P Components Interface

| NickName | Icon | Description (for icon generation) |
| --- | --- | --- |
| `PassportToD2P` | yes | Converts CSC passport JSON into an in-memory D2P `GHComponent` (type id from the IFC class, canonical or placed geometry, authored shapes, capture markers) with nested Member geometry trees and the convention user text. |
| `ReadFromD2P` | yes | Reads D2P components (and tagged pieces of `BakeComponents`) in the Rhino document back into passport JSON with `csc_placement` from the component plane. |

---

## Removed / renamed components

These no longer appear in `grasshopper_userobjects_src/` or `grasshopper_userobjects_xml/`. Prefer icons for their replacements; only create legacy icons if old definitions still ship them.

| Former NickName | Status | Icon | Replacement | Notes |
| --- | --- | --- | --- | --- |
| `ComposeToD2P` | renamed | **missing** | `PassportToD2P` | Same role; use `PassportToD2P.svg`. |
| `FetchGeometry` | removed | **missing** | `FetchOriginalGeometry` / `FetchReducedGeometry` | Legacy combined geometry fetch. |
| `GetComponentData` | renamed | yes | `GetComponentPassport` | Same artwork. |
| `CSC_AddComponent` | removed | **missing** | `AddComponentIdentity` | Legacy POST of full component JSON + OBJ uploads. |
| `CSC_CreateComponent` | removed | **missing** | `CreateComponentIdentity` | Legacy builder for complete component JSON from Rhino geometry. |
| `CSC_ArrangeComponents` | removed | **missing** | `CreateArrangement` | Legacy grid arrangement from component bounding boxes. |
| `FetchDetailedGeometry` | renamed | yes | `FetchOriginalGeometry` | Decision 8.23: the level is called Original. |
| `ApplyPCAFrame` | renamed | yes | `ApplyFrame` | The frame is the server's, not a PCA (decision 7.10). |
| `CreateReinforcement` | renamed | yes | `ReinforcementLayout` | Reinforcement is evidence now (decision 7.8). |
| `CreateDesign`, `AddDesign`, `FetchDesign` | removed | yes | --- | Designs are not part of CSC (decision 7.11). |

---

## References

- [Grasshopper Icons (McNeel developer guide)](https://developer.rhino3d.com/en/guides/grasshopper/grasshopper-icons/)
- [Grasshopper_Icon_Set.zip](https://developer.rhino3d.com/en/guides/grasshopper/grasshopper-icons/) -> official vector reference
- Component source: `grasshopper_userobjects_src/`
- SubCategory numbering: `grasshopper_development/README.md`
