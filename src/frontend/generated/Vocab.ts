// Auto-generated from backend GET /vocab
// Generated on: 2026-10-05T18:37:45.706Z
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

export type OriginKind = 'deinstallation' | 'demolition' | 'offcut' | 'surplus' | 'unknown'
export const ORIGIN_KIND_LABELS: Record<OriginKind, string> = {
  "deinstallation": "Deinstalled",
  "demolition": "Recovered from demolition",
  "offcut": "Production offcut",
  "surplus": "Surplus",
  "unknown": "Unknown",
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

export type Status = 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn'
export const STATUS_LABELS: Record<Status, string> = {
  "draft": "draft",
  "pending": "pending",
  "published": "published",
  "rejected": "rejected",
  "withdrawn": "withdrawn",
}

export type Precision = 'exact' | 'day' | 'month' | 'year' | 'unknown'
export const PRECISION_LABELS: Record<Precision, string> = {
  "exact": "exact",
  "day": "day",
  "month": "month",
  "year": "year",
  "unknown": "unknown",
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

export type ConstructionMethod = 'monolithic' | 'prefabricated' | 'mixed' | 'unknown'
export const CONSTRUCTION_METHOD_LABELS: Record<ConstructionMethod, string> = {
  "monolithic": "Monolithic (cast in place)",
  "prefabricated": "Prefabricated",
  "mixed": "Mixed",
  "unknown": "Unknown",
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

export type ChangeCause = 'patch' | 'inherited_from_parent' | 'material_merge' | 'exit' | 'reenter' | 'withdraw' | 'reinstate' | 'migration' | 'derived_exit' | 'deinstall' | 'undo_deinstall'
export const CHANGE_CAUSE_LABELS: Record<ChangeCause, string> = {
  "patch": "Edited",
  "inherited_from_parent": "Taken over from a parent",
  "material_merge": "Material merged",
  "exit": "Circulation changed",
  "reenter": "Re-entered circulation",
  "withdraw": "Withdrawn",
  "reinstate": "Reinstated",
  "migration": "Migration",
  "derived_exit": "Cut into pieces",
  "deinstall": "Deinstalled",
  "undo_deinstall": "Deinstallation undone",
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

export type SourceTier = 'destructive' | 'ndt' | 'archival' | 'visual' | 'heuristic' | 'inherited'
export const SOURCE_TIER_LABELS: Record<SourceTier, string> = {
  "destructive": "Destructive test",
  "ndt": "Non-destructive test",
  "archival": "Archival document",
  "visual": "Visual inspection",
  "heuristic": "Estimate",
  "inherited": "Inherited from a parent",
}

export type VerificationState = 'unverified' | 'self_attested' | 'reviewed' | 'accredited'
export const VERIFICATION_STATE_LABELS: Record<VerificationState, string> = {
  "unverified": "Unverified",
  "self_attested": "Self-attested",
  "reviewed": "Reviewed",
  "accredited": "Accredited",
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

/** Display label of a vocabulary value; unknown values pass through. */
export function vocabLabel(labels: Record<string, string>, value?: string | null): string {
  if (!value) return ''
  return labels[value] ?? value
}
