// Auto-generated from backend GET /vocab
// Generated on: 2026-10-02T13:41:52.772Z
// Source: http://127.0.0.1:8000/vocab

export type OriginalFunction = 'IfcBeam' | 'IfcColumn' | 'IfcSlab' | 'IfcPlate' | 'IfcWall' | 'IfcMember' | 'IfcPipeSegment' | 'IfcFooting' | 'IfcDiscreteAccessory' | 'IfcBuildingElementPart' | 'IfcBuildingElementProxy' | 'CscDebris'
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
  "IfcBuildingElementProxy": "Unknown",
  "CscDebris": "Debris",
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

export type ChangeCause = 'patch' | 'inherited_from_parent' | 'material_merge' | 'exit' | 'reenter' | 'withdraw' | 'reinstate' | 'migration' | 'derived_exit'
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
}

/** Display label of a vocabulary value; unknown values pass through. */
export function vocabLabel(labels: Record<string, string>, value?: string | null): string {
  if (!value) return ''
  return labels[value] ?? value
}
