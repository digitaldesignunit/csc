// Auto-generated from backend GET /vocab
// Generated on: 2026-10-28T15:20:51.630Z
// Source: http://127.0.0.1:8791/vocab

export type OriginalFunction = 'IfcBeam' | 'IfcColumn' | 'IfcSlab' | 'IfcPlate' | 'IfcWall' | 'IfcMember' | 'IfcPipeSegment' | 'IfcFooting' | 'IfcDiscreteAccessory' | 'IfcBuildingElementPart' | 'IfcWindow' | 'IfcDoor' | 'IfcStair' | 'IfcRailing' | 'IfcDuctSegment' | 'IfcBuildingElementProxy' | 'CscDebris'
export const ORIGINAL_FUNCTION_LABELS: Record<OriginalFunction, string> = {
  "IfcBeam": "Beam",
  "IfcColumn": "Column",
  "IfcSlab": "Slab",
  "IfcPlate": "Plate / Panel",
  "IfcWall": "Wall",
  "IfcMember": "Member",
  "IfcPipeSegment": "Pipe",
  "IfcFooting": "Footing",
  "IfcDiscreteAccessory": "Accessory / Connector",
  "IfcBuildingElementPart": "Element part (masonry unit, ...)",
  "IfcWindow": "Window",
  "IfcDoor": "Door / gate",
  "IfcStair": "Stair",
  "IfcRailing": "Railing / balustrade",
  "IfcDuctSegment": "Duct",
  "IfcBuildingElementProxy": "Unknown",
  "CscDebris": "Debris",
}

export const ORIGINAL_FUNCTION_DESCRIPTIONS: Record<OriginalFunction, string> = {
  "IfcBeam": "A horizontal load-bearing member that spans between supports.",
  "IfcColumn": "A vertical load-bearing member.",
  "IfcSlab": "A horizontal load-bearing plate, such as a floor or roof slab.",
  "IfcPlate": "A flat, non-load-bearing sheet or panel, such as a cladding or worktop panel.",
  "IfcWall": "A vertical element that divides or encloses space.",
  "IfcMember": "A long element that is neither beam nor column, such as bracing or a purlin.",
  "IfcPipeSegment": "A length of pipe.",
  "IfcFooting": "A foundation element that carries load into the ground.",
  "IfcDiscreteAccessory": "A small fitting or connector, such as a bracket or an anchor.",
  "IfcBuildingElementPart": "A unit that makes up a larger element, such as a whole brick or block.",
  "IfcWindow": "A window, with or without its frame.",
  "IfcDoor": "A door or gate, with or without its frame.",
  "IfcStair": "A stair, an assembly of flights, landings and supports.",
  "IfcRailing": "A railing or balustrade.",
  "IfcDuctSegment": "A length of ventilation duct.",
  "IfcBuildingElementProxy": "The former function is not known.",
  "CscDebris": "No former function as a single element: rubble, aggregate, fragments.",
}

export type ShapeClassHint = 'IfcBeam' | 'IfcColumn' | 'IfcSlab' | 'IfcPlate' | 'IfcWall' | 'IfcMember' | 'IfcPipeSegment' | 'IfcFooting' | 'IfcDiscreteAccessory' | 'IfcBuildingElementPart' | 'IfcWindow' | 'IfcDoor' | 'IfcStair' | 'IfcRailing' | 'IfcDuctSegment' | 'CscDebris'
export const SHAPE_CLASS_HINT_LABELS: Record<ShapeClassHint, string> = {
  "IfcBeam": "linear",
  "IfcColumn": "linear",
  "IfcSlab": "planar",
  "IfcPlate": "planar",
  "IfcWall": "planar",
  "IfcMember": "linear",
  "IfcPipeSegment": "linear",
  "IfcFooting": "block",
  "IfcDiscreteAccessory": "composite",
  "IfcBuildingElementPart": "block",
  "IfcWindow": "planar",
  "IfcDoor": "planar",
  "IfcStair": "composite",
  "IfcRailing": "planar",
  "IfcDuctSegment": "linear",
  "CscDebris": "irregular",
}

export type ShapeClass = 'linear' | 'planar' | 'block' | 'irregular' | 'composite'
export const SHAPE_CLASS_LABELS: Record<ShapeClass, string> = {
  "linear": "Linear",
  "planar": "Planar",
  "block": "Block",
  "irregular": "Irregular",
  "composite": "Composite",
}

export const SHAPE_CLASS_DESCRIPTIONS: Record<ShapeClass, string> = {
  "linear": "One extent is much larger than the other two, like a beam or a column.",
  "planar": "Two extents are much larger than the third, like a panel or a slab.",
  "block": "Three comparable extents, like a brick or a footing.",
  "irregular": "No simple shape describes it, like rubble or a natural stone.",
  "composite": "Several distinct bodies or branches, like a stair. Always set by hand.",
}

export type OriginKind = 'deinstallation' | 'demolition' | 'offcut' | 'surplus' | 'unknown'
export const ORIGIN_KIND_LABELS: Record<OriginKind, string> = {
  "deinstallation": "Deinstalled",
  "demolition": "Recovered from demolition",
  "offcut": "Production offcut",
  "surplus": "Surplus",
  "unknown": "Unknown",
}

export const ORIGIN_KIND_DESCRIPTIONS: Record<OriginKind, string> = {
  "deinstallation": "Taken out of a construction work in which it was installed.",
  "demolition": "Recovered from demolition output, not taken out as a single element.",
  "offcut": "Residue of a fabrication process; it was never installed.",
  "surplus": "An unused whole product: overstock, a return or a site leftover.",
  "unknown": "Where the element came from is not recorded.",
}

export type ExitKind = 'split' | 'merged' | 'installed' | 'recycled' | 'disposed' | 'returned' | 'lost'
export const EXIT_KIND_LABELS: Record<ExitKind, string> = {
  "split": "Split",
  "merged": "Merged",
  "installed": "Installed",
  "recycled": "Recycled",
  "disposed": "Disposed",
  "returned": "Returned",
  "lost": "Lost",
}

export const EXIT_KIND_DESCRIPTIONS: Record<ExitKind, string> = {
  "split": "Cut into smaller elements; they are catalogued as children of this element.",
  "merged": "Joined with other elements into a new element, which is catalogued as its child.",
  "installed": "Built into a construction work. The element still exists and may come back.",
  "recycled": "The material was recovered, for example crushed or melted; the element is gone.",
  "disposed": "Disposed of as waste.",
  "returned": "Given back to its owner or supplier. The element exists but left the custody of the catalog.",
  "lost": "Its whereabouts are not recorded.",
}

export type Status = 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn'
export const STATUS_LABELS: Record<Status, string> = {
  "draft": "draft",
  "pending": "pending",
  "published": "published",
  "rejected": "rejected",
  "withdrawn": "withdrawn",
}

export const STATUS_DESCRIPTIONS: Record<Status, string> = {
  "draft": "Still being prepared. Only its author and the moderators of the dataset see it.",
  "pending": "Submitted and waiting for a moderator to publish or reject it.",
  "published": "Accepted by a moderator. It is listed and its results count.",
  "rejected": "Not accepted by a moderator. It can be reworked and submitted again.",
  "withdrawn": "Taken out of the catalog after it was published. Other users see only a marker.",
}

export type Precision = 'exact' | 'day' | 'month' | 'year' | 'unknown'
export const PRECISION_LABELS: Record<Precision, string> = {
  "exact": "exact",
  "day": "day",
  "month": "month",
  "year": "year",
  "unknown": "unknown",
}

export const PRECISION_DESCRIPTIONS: Record<Precision, string> = {
  "exact": "The time is known to the minute.",
  "day": "Only the day is known.",
  "month": "Only the month is known.",
  "year": "Only the year is known.",
  "unknown": "The time is not known; the value is a placeholder.",
}

export type DgnbClass = 'optimised' | 'improved' | 'standard' | 'limited' | 'problematic' | 'not_assessable'
export const DGNB_CLASS_LABELS: Record<DgnbClass, string> = {
  "optimised": "Optimised",
  "improved": "Improved",
  "standard": "Standard",
  "limited": "Limited",
  "problematic": "Problematic",
  "not_assessable": "Assessment not possible",
}

export const DGNB_CLASS_DESCRIPTIONS: Record<DgnbClass, string> = {
  "optimised": "Loose or click connection, no tools, removable without damage; one material, fully circular.",
  "improved": "Inserted, plugged or screwed, simple tools, removable without damage.",
  "standard": "Permanently installed (nailed, bolted), standard tools, mostly removable.",
  "limited": "Permanently installed (soldered, foamed, sealed), high effort, special tools.",
  "problematic": "Permanently installed (adhesive, welded), extremely complex or not feasible to separate.",
  "not_assessable": "An assessment is not possible, or it cannot be dismantled.",
}

export type ConnectionType = 'loose' | 'click' | 'inserted' | 'plugged' | 'screwed' | 'nailed' | 'bolted' | 'soldered' | 'foamed' | 'sealed' | 'adhesive' | 'welded' | 'cast_in' | 'grouted' | 'other' | 'unknown'
export const CONNECTION_TYPE_LABELS: Record<ConnectionType, string> = {
  "loose": "Loose",
  "click": "Click",
  "inserted": "Inserted",
  "plugged": "Plugged",
  "screwed": "Screwed",
  "nailed": "Nailed",
  "bolted": "Bolted",
  "soldered": "Soldered",
  "foamed": "Foamed",
  "sealed": "Sealed",
  "adhesive": "Adhesive",
  "welded": "Welded",
  "cast_in": "Cast in",
  "grouted": "Grouted",
  "other": "Other",
  "unknown": "Unknown",
}

export const CONNECTION_TYPE_DESCRIPTIONS: Record<ConnectionType, string> = {
  "loose": "Resting in place, not fixed.",
  "click": "Held by a click or snap fit.",
  "inserted": "Pushed or slid into a seat.",
  "plugged": "Held by a plug or dowel.",
  "screwed": "Fixed with screws.",
  "nailed": "Fixed with nails.",
  "bolted": "Fixed with bolts.",
  "soldered": "Joined by solder.",
  "foamed": "Fixed with foam.",
  "sealed": "Joined with a sealant.",
  "adhesive": "Glued.",
  "welded": "Joined by welding.",
  "cast_in": "Cast into the concrete as one body.",
  "grouted": "Joined with grout in a joint or a pocket.",
  "other": "Another kind of connection.",
  "unknown": "The connection is not known.",
}

export type ConstructionMethod = 'monolithic' | 'prefabricated' | 'mixed' | 'unknown'
export const CONSTRUCTION_METHOD_LABELS: Record<ConstructionMethod, string> = {
  "monolithic": "Monolithic (cast in place)",
  "prefabricated": "Prefabricated",
  "mixed": "Mixed",
  "unknown": "Unknown",
}

export const CONSTRUCTION_METHOD_DESCRIPTIONS: Record<ConstructionMethod, string> = {
  "monolithic": "Cast in place as one body on site.",
  "prefabricated": "Made in a factory and assembled on site.",
  "mixed": "Partly cast in place, partly prefabricated.",
  "unknown": "The construction method is not known.",
}

export type MaterialGroup = 'mineral' | 'metal' | 'bio-based' | 'polymer' | 'bituminous' | 'insulation' | 'other'
export const MATERIAL_GROUP_LABELS: Record<MaterialGroup, string> = {
  "mineral": "mineral",
  "metal": "metal",
  "bio-based": "bio-based",
  "polymer": "polymer",
  "bituminous": "bituminous",
  "insulation": "insulation",
  "other": "other",
}

export const MATERIAL_GROUP_DESCRIPTIONS: Record<MaterialGroup, string> = {
  "mineral": "Concrete, brick, stone, ceramic, gypsum and glass.",
  "metal": "Steel, aluminium, copper, zinc, lead and iron.",
  "bio-based": "Timber, engineered wood, wood-based panels, bamboo and plant fibre.",
  "polymer": "Plastics and plastic composites, such as acrylic, PVC and solid surface.",
  "bituminous": "Asphalt and bituminous membranes.",
  "insulation": "Mineral wool and polymer foam insulation.",
  "other": "Mixed or composite elements, and materials not known.",
}

export type InheritUnit = 'origin' | 'manufactured_at' | 'material' | 'trade_name' | 'manufacturer' | 'material_separability' | 'original_function'
export const INHERIT_UNIT_LABELS: Record<InheritUnit, string> = {
  "origin": "Origin",
  "manufactured_at": "Manufactured",
  "material": "Material and waste class",
  "trade_name": "Trade name",
  "manufacturer": "Manufacturer",
  "material_separability": "Material separability",
  "original_function": "Original function",
}

export type ChangeCause = 'patch' | 'inherited_from_parent' | 'material_merge' | 'exit' | 'reenter' | 'withdraw' | 'reinstate' | 'migration' | 'derived_exit' | 'deinstall' | 'undo_deinstall' | 'verify' | 'publish' | 'attach' | 'redact'
export const CHANGE_CAUSE_LABELS: Record<ChangeCause, string> = {
  "patch": "Edited",
  "inherited_from_parent": "Taken over from a parent",
  "material_merge": "Material merged",
  "exit": "Circulation changed",
  "reenter": "Re-entered circulation",
  "withdraw": "Withdrawn",
  "reinstate": "Reinstated",
  "migration": "Migration",
  "derived_exit": "Cut into elements",
  "deinstall": "Deinstalled",
  "undo_deinstall": "Deinstallation undone",
  "verify": "Verification changed",
  "publish": "Published",
  "attach": "File attached",
  "redact": "File removed",
}

export type EvidenceMethod = 'rebound_hammer' | 'core_compression' | 'archival_document' | 'visual_inspection' | 'era_heuristic' | 'manufacturer_datasheet' | 'reinforcement_layout'
export const EVIDENCE_METHOD_LABELS: Record<EvidenceMethod, string> = {
  "rebound_hammer": "Rebound hammer",
  "core_compression": "Core in compression",
  "archival_document": "Archival document",
  "visual_inspection": "Visual inspection",
  "era_heuristic": "Rule of thumb (era, region, typology)",
  "manufacturer_datasheet": "Manufacturer datasheet",
  "reinforcement_layout": "Reinforcement layout",
}

export const EVIDENCE_METHOD_DESCRIPTIONS: Record<EvidenceMethod, string> = {
  "rebound_hammer": "A rebound hammer test of concrete: at least nine readings, no strength by itself.",
  "core_compression": "A drilled core crushed in a press; a destructive test with a measured strength.",
  "archival_document": "A drawing, report, type plate or marking that documents the element; it may carry a claim.",
  "visual_inspection": "An observation of the condition: cracks, spalling, corrosion or an overall grade.",
  "era_heuristic": "An estimate from the year of construction, the regional practice or the type.",
  "manufacturer_datasheet": "A claim from the manufacturer of the product.",
  "reinforcement_layout": "The reinforcement bars of the element as centre lines in its coordinates.",
}

export type SourceTier = 'destructive' | 'ndt' | 'archival' | 'visual' | 'heuristic' | 'inherited'
export const SOURCE_TIER_LABELS: Record<SourceTier, string> = {
  "destructive": "Destructive test",
  "ndt": "Non-destructive test",
  "archival": "Archival document",
  "visual": "Visual inspection",
  "heuristic": "Estimate",
  "inherited": "Inherited from a parent",
}

export const SOURCE_TIER_DESCRIPTIONS: Record<SourceTier, string> = {
  "destructive": "A test that destroys a sample. For most quantities the most trusted source.",
  "ndt": "A test that leaves the element intact, with an instrument.",
  "archival": "A claim from a document, a drawing or a datasheet.",
  "visual": "An observation by a person.",
  "heuristic": "An estimate from rules of thumb. The least trusted source.",
  "inherited": "Taken over from a parent element, with a lower confidence.",
}

export type VerificationState = 'unverified' | 'self_attested' | 'reviewed' | 'accredited'
export const VERIFICATION_STATE_LABELS: Record<VerificationState, string> = {
  "unverified": "Unverified",
  "self_attested": "Self-attested",
  "reviewed": "Reviewed",
  "accredited": "Accredited",
}

export const VERIFICATION_STATE_DESCRIPTIONS: Record<VerificationState, string> = {
  "unverified": "No one has confirmed it yet. It counts with a low weight.",
  "self_attested": "A person who did the work and recorded it stands by it.",
  "reviewed": "A second person with the reviewer role confirmed it.",
  "accredited": "Confirmed, and made by an organisation accredited for the standard.",
}

export type Quantity = 'compressive_strength' | 'compressive_strength_in_situ' | 'rebound_number' | 'q_value' | 'density' | 'rebar_diameter' | 'rebar_spec' | 'concrete_class' | 'steel_grade' | 'cover_depth' | 'exposure_class' | 'chloride_content' | 'elastic_modulus' | 'mass' | 'carbonation_depth' | 'spalling' | 'cracking' | 'corrosion' | 'moisture_content' | 'crack_width' | 'condition_grade'
export const QUANTITY_LABELS: Record<Quantity, string> = {
  "compressive_strength": "Compressive strength",
  "compressive_strength_in_situ": "In-situ compressive strength",
  "rebound_number": "Rebound number R",
  "q_value": "Q-value",
  "density": "Density",
  "rebar_diameter": "Rebar diameter",
  "rebar_spec": "Rebar steel grade",
  "concrete_class": "Concrete strength class",
  "steel_grade": "Steel grade (EN 10025)",
  "cover_depth": "Concrete cover",
  "exposure_class": "Exposure class",
  "chloride_content": "Chloride content",
  "elastic_modulus": "Elastic modulus",
  "mass": "Mass",
  "carbonation_depth": "Carbonation depth",
  "spalling": "Spalling",
  "cracking": "Cracking",
  "corrosion": "Corrosion",
  "moisture_content": "Moisture content",
  "crack_width": "Widest crack",
  "condition_grade": "Condition grade",
}

export const QUANTITY_DESCRIPTIONS: Record<Quantity, string> = {
  "compressive_strength": "Compressive strength of the material (MPa), from a test, a document or an estimate.",
  "compressive_strength_in_situ": "Strength estimated for the concrete in the structure (MPa).",
  "rebound_number": "Median rebound reading of a hammer test, a whole number.",
  "q_value": "Median rebound reading of a Q-type hammer, a whole number.",
  "density": "Mass per volume of the material (kg/m3).",
  "rebar_diameter": "Diameter of the reinforcement bars (mm).",
  "rebar_spec": "Steel grade of the reinforcement bars, as named on a drawing or a datasheet.",
  "concrete_class": "Strength class of the concrete, such as C25/30 or B225.",
  "steel_grade": "Structural steel grade: S235, S275, S355, S460 or other.",
  "cover_depth": "Concrete cover over the reinforcement (mm).",
  "exposure_class": "Exposure class of the concrete after EN 206, such as XC3.",
  "chloride_content": "Chloride content, as a percentage of the mass of cement.",
  "elastic_modulus": "Stiffness of the material (GPa).",
  "mass": "Weight of the element in this state (kg).",
  "carbonation_depth": "Depth to which the concrete is carbonated (mm).",
  "spalling": "Severity of spalled concrete, from 0 (none) to 3 (severe).",
  "cracking": "Severity of cracking, from 0 (none) to 3 (severe).",
  "corrosion": "Severity of corrosion, from 0 (none) to 3 (severe).",
  "moisture_content": "Water content of the material (%).",
  "crack_width": "Width of the widest crack (mm).",
  "condition_grade": "Overall condition, from 3 (good) to 0 (unusable as it is).",
}

/** Display label of a vocabulary value; unknown values pass through. */
export function vocabLabel(labels: Record<string, string>, value?: string | null): string {
  if (!value) return ''
  return labels[value] ?? value
}
