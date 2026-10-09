/**
 * The pure parts of the Materials admin page (plan P11 stage 3, decision 8.118
 * S6): which rows show for the search and the retired / merged switch.
 */
import { MATERIAL_GROUP_LABELS, vocabLabel } from '@/generated/Vocab'

type MaterialLike = {
  _id: string
  label: string
  group: string
  default_class?: string | null
  uniclass?: string | null
  notes?: string | null
  retired?: boolean | null
  merged_into?: string | null
}

export function isLive(material: MaterialLike): boolean {
  return !material.retired && !material.merged_into
}

export function groupLabel(group: string): string {
  return vocabLabel(MATERIAL_GROUP_LABELS, group)
}

/** The rows to show: the live ones, or all with `showAll`, narrowed by the
 *  search (label, id, group, waste class, Uniclass or notes). */
export function filterMaterials<T extends MaterialLike>(materials: T[], query: string, showAll: boolean): T[] {
  const needle = query.trim().toLowerCase()
  return materials.filter((m) => {
    if (!showAll && !isLive(m)) return false
    if (!needle) return true
    return [m.label, m._id, groupLabel(m.group), m.group, m.default_class, m.uniclass, m.notes]
      .some((text) => (text ?? '').toLowerCase().includes(needle))
  })
}

export function hiddenCount(materials: MaterialLike[]): number {
  return materials.filter((m) => !isLive(m)).length
}

/** "retired" or "merged into X", empty for a live material. */
export function stateNote(material: MaterialLike): string {
  if (material.merged_into) return `merged into ${material.merged_into}`
  return material.retired ? 'retired' : ''
}
