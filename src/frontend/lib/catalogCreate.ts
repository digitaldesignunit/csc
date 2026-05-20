import type { ComponentLocation } from '@/generated/ComponentModel'

export const COMPONENT_TYPES = [
  'panel',
  'beam',
  'column',
  'slab',
  'rubble',
  'brick',
  'pipe',
  'profile',
  'connector',
  'other',
] as const

export const CONDITION_VALUES = [0, 1, 2, 3] as const
export const MANUFACTURED_PRECISIONS = ['exact', 'month', 'year', 'unknown'] as const

/** Select value: pick a custom material/dataset string in a follow-up field. */
export const CATALOG_META_CUSTOM = '__custom__'

export const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export type AddComponentFormState = {
  name: string
  type: string
  material: string
  dataset: string
  complexity: number
  fragment: boolean
  assembly: boolean
  colorR: number
  colorG: number
  colorB: number
  lat: number
  lon: number
  /** Text inputs for L/W/H (mm); parsed on submit so fields can be cleared while typing. */
  lengthMm: string
  widthMm: string
  heightMm: string
  condition: number | null
  manufactured_at: string
  manufactured_precision: string
  salvage_source: string
  salvaged_at: string
  parent_component: string
  notes: string
  quantity: number
}

export const defaultAddComponentFormState = (): AddComponentFormState => ({
  name: '',
  type: 'panel',
  material: '',
  dataset: '',
  complexity: 2,
  fragment: false,
  assembly: false,
  colorR: 110,
  colorG: 110,
  colorB: 110,
  lat: 0,
  lon: 0,
  lengthMm: '100',
  widthMm: '100',
  heightMm: '10',
  condition: null,
  manufactured_at: '',
  manufactured_precision: '',
  salvage_source: '',
  salvaged_at: '',
  parent_component: '',
  notes: '',
  quantity: 1,
})

/** Label shown in review when the user leaves name empty. */
export function addComponentDisplayNamePreview(name: string): string {
  const trimmed = name.trim()
  if (trimmed) return trimmed
  return 'Auto-generated (catalog number)'
}

export function catalogMetaSelectValue(
  value: string,
  options: string[],
): string {
  if (!value.trim()) return ''
  return options.includes(value) ? value : CATALOG_META_CUSTOM
}

function axisAlignedFrame() {
  return {
    o: [0, 0, 0],
    x: [1, 0, 0],
    y: [0, 1, 0],
    z: [0, 0, 1],
  }
}

/** Parse a dimension text field; returns NaN when empty or invalid. */
export function parseDimensionMm(value: string): number {
  const trimmed = value.trim().replace(',', '.')
  if (!trimmed) return Number.NaN
  return parseFloat(trimmed)
}

/** Allow empty and partial decimals while the user types (e.g. "12.", ".5"). */
export function sanitizeDimensionInput(value: string): string {
  const v = value.replace(',', '.')
  if (v === '') return ''
  if (/^\d*\.?\d*$/.test(v)) return v
  return v.slice(0, -1)
}

export function buildBoxExtrusionFromDimensions(lengthMm: number, widthMm: number, heightMm: number) {
  const l = Math.max(0.1, lengthMm)
  const w = Math.max(0.1, widthMm)
  const h = Math.max(0.1, heightMm)
  const hx = l / 2
  const hy = w / 2

  return {
    geometry: {
      extrusions: [
        {
          profile: [
            [-hx, -hy],
            [hx, -hy],
            [hx, hy],
            [-hx, hy],
          ],
          height: h,
        },
      ],
    },
    bbx: [l, w, h] as [number, number, number],
    bbx_origin: [0, 0, 0] as [number, number, number],
    iframe: axisAlignedFrame(),
    pca_frame: axisAlignedFrame(),
  }
}

function dateInputToIso(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return `${trimmed}T00:00:00Z`
  }
  return trimmed
}

export type CreateIdentityPayload = Record<string, unknown>

export function buildCreateIdentityPayload(
  identityId: string,
  form: AddComponentFormState,
): CreateIdentityPayload {
  const box = buildBoxExtrusionFromDimensions(
    parseDimensionMm(form.lengthMm),
    parseDimensionMm(form.widthMm),
    parseDimensionMm(form.heightMm),
  )

  const location: ComponentLocation = {
    lat: form.lat,
    lon: form.lon,
  }

  const trimmedName = form.name.trim()

  const payload: CreateIdentityPayload = {
    _id: identityId,
    type: form.type,
    material: form.material.trim(),
    dataset: form.dataset.trim(),
    complexity: form.complexity,
    fragment: form.fragment,
    assembly: form.assembly,
    color: [form.colorR, form.colorG, form.colorB],
    location,
    descriptors: {},
    processes: {},
    validated: false,
    reserved: '',
    attributes: {},
    ...box,
  }

  if (trimmedName) {
    payload.name = trimmedName
  }

  if (form.condition !== null) {
    payload.condition = form.condition
  }

  const manufacturedAt = dateInputToIso(form.manufactured_at)
  if (manufacturedAt) payload.manufactured_at = manufacturedAt
  if (form.manufactured_precision.trim()) {
    payload.manufactured_precision = form.manufactured_precision.trim()
  }
  const salvagedAt = dateInputToIso(form.salvaged_at)
  if (salvagedAt) payload.salvaged_at = salvagedAt
  if (form.salvage_source.trim()) {
    payload.salvage_source = form.salvage_source.trim()
  }
  if (form.parent_component.trim() && UUID_REGEX.test(form.parent_component.trim())) {
    payload.parent_identities = [form.parent_component.trim()]
  }

  const notes = form.notes.trim()
  if (notes) {
    payload.notes = notes
  }

  const qty = Math.max(1, Math.floor(form.quantity))
  if (qty !== 1) {
    payload.quantity = qty
  }

  return payload
}

export function normalizeScannedIdentityId(raw: string): string {
  return raw.trim()
}

export function isValidIdentityUuid(value: string): boolean {
  return UUID_REGEX.test(value.trim())
}
