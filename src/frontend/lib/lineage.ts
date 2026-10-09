'use client'

/**
 * Shared helpers of the provenance, circulation and lineage forms (spec
 * section 3.1.1 -- 3.1.3, decisions 8.31 -- 8.38; plan P4).
 */
import { useEffect, useState } from 'react'

import type {
  CircularityClass,
  ComponentIdentity,
  ConstructionWork,
  Origin,
} from '@/generated/CatalogModels'
import type { Material } from '@/generated/LineageModels'
import type { InheritUnit } from '@/generated/Vocab'
import { backendJson } from '@/lib/backend'

/**
 * The fields of each inheritance unit; a unit moves as a whole (8.32).
 * Mirrors `INHERIT_UNITS` in the backend's `vocab.py`.
 */
export const INHERIT_UNIT_FIELDS: Record<InheritUnit, (keyof ComponentIdentity)[]> = {
  origin: ['origin'],
  manufactured_at: ['manufactured_at', 'manufactured_precision'],
  material: ['material', 'material_class', 'material_class_source'],
  trade_name: ['trade_name'],
  manufacturer: ['manufacturer'],
  material_separability: ['material_separability'],
  original_function: ['original_function'],
}

export const INHERIT_UNITS = Object.keys(INHERIT_UNIT_FIELDS) as InheritUnit[]

/** Origin kinds that may name the works, position and connections (I16). */
export const WORKS_ORIGIN_KINDS: Origin['kind'][] = ['deinstallation', 'demolition']

/** Exits that end a piece for good: no re-entry (I18). */
export const TERMINAL_EXIT_KINDS = ['recycled', 'disposed', 'split', 'merged']

/** The exits open to a piece still in place: it never left its works (8.104). */
export const IN_PLACE_EXIT_KINDS = ['recycled', 'disposed', 'lost'] as const

/** Exits a cut may start from besides none: already cut (8.34). */
export const CUTTABLE_EXIT_KINDS = ['split', 'merged']

/** Exits a moderator sets by hand; `merged` is only ever set by the server (8.8). */
export const MANUAL_EXIT_KINDS = ['installed', 'recycled', 'disposed', 'returned', 'lost', 'split'] as const

export function isInherited(identity: ComponentIdentity, unit: InheritUnit): boolean {
  return (identity.inherited_fields ?? []).includes(unit)
}

/** `YYYY-MM-DD` from a stored timestamp, for the date fields. */
export function isoToDateOnly(value: string | null | undefined): string {
  return value ? String(value).slice(0, 10) : ''
}

/** A date field's `YYYY-MM-DD` as a timestamp; empty stays null. */
export function dateOnlyToIso(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  return /^\d{4}-\d{2}-\d{2}$/.test(trimmed) ? `${trimmed}T00:00:00Z` : trimmed
}

export function emptyOrigin(): Origin {
  return { kind: 'unknown', at: null, at_precision: 'unknown', connection_types: [], performed_by: [] }
}

function blank(value: string | null | undefined): boolean {
  return !value || value.trim().length === 0
}

function cleanWork(work: ConstructionWork | null | undefined): ConstructionWork | null {
  if (!work || blank(work.name)) return null
  return {
    name: work.name.trim(),
    identifier: blank(work.identifier) ? null : work.identifier!.trim(),
    year_built: typeof work.year_built === 'number' && Number.isFinite(work.year_built) ? work.year_built : null,
    use: blank(work.use) ? null : work.use!.trim(),
    construction_method: work.construction_method ?? null,
  }
}

/**
 * The origin as the backend takes it: empty strings dropped, and the
 * works-related fields only for deinstallation / demolition (I16).
 */
export function cleanOrigin(origin: Origin): Origin {
  const works = WORKS_ORIGIN_KINDS.includes(origin.kind)
  const place = origin.place && (!blank(origin.place.name) || !blank(origin.place.address) || origin.place.location)
    ? {
        name: blank(origin.place.name) ? null : origin.place.name!.trim(),
        address: blank(origin.place.address) ? null : origin.place.address!.trim(),
        location: origin.place.location ?? null,
      }
    : null
  return {
    kind: origin.kind,
    planned: works && origin.planned === true,
    at: origin.at || null,
    at_precision: origin.at ? origin.at_precision ?? 'exact' : 'unknown',
    place,
    construction_work: works ? cleanWork(origin.construction_work) : null,
    position_in_work: works && !blank(origin.position_in_work) ? origin.position_in_work!.trim() : null,
    connection_types: works ? origin.connection_types ?? [] : [],
    detachability: works ? origin.detachability ?? null : null,
    method: blank(origin.method) ? null : origin.method!.trim(),
    performed_by: origin.performed_by ?? [],
    notes: blank(origin.notes) ? null : origin.notes!.trim(),
  }
}

/** Compare two JSON values regardless of key order. */
export function sameJson(a: unknown, b: unknown): boolean {
  return canonical(a) === canonical(b)
}

function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, v) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([x], [y]) => x.localeCompare(y)))
      : v,
  )
}

/** A DGNB class set by the signed-in user names them as assessor. */
export function assessedClass(
  next: CircularityClass | null,
  previous: CircularityClass | null | undefined,
  userId: string | undefined,
): CircularityClass | null {
  if (!next) return null
  const note = blank(next.note) ? null : next.note!.trim()
  if (previous && previous.class === next.class) {
    return { ...previous, note }
  }
  return {
    class: next.class,
    assessed_by: userId ? [{ kind: 'user', user_id: userId }] : [],
    note,
  }
}

/** The materials list (2.10); retired ones on request, for existing values. */
export function useMaterials(includeRetired = false): Material[] {
  const [materials, setMaterials] = useState<Material[]>([])
  useEffect(() => {
    let cancelled = false
    backendJson<Material[]>(`/materials${includeRetired ? '?include_retired=true' : ''}`)
      .then((rows) => {
        if (!cancelled) setMaterials(rows)
      })
      .catch(() => {
        if (!cancelled) setMaterials([])
      })
    return () => {
      cancelled = true
    }
  }, [includeRetired])
  return materials
}
