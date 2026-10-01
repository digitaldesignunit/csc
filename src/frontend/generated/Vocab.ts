// Auto-generated from backend GET /vocab
// Generated on: 2026-10-01T19:18:13.855Z
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

/** Display label of a vocabulary value; unknown values pass through. */
export function vocabLabel(labels: Record<string, string>, value?: string | null): string {
  if (!value) return ''
  return labels[value] ?? value
}
