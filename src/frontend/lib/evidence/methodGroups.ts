/**
 * The grouped method choice of the evidence form (decision 8.134 b): the
 * methods by what kind of evidence they give, with a search. Structure only;
 * labels and descriptions are the registry's (decision 7.1).
 *
 * Run: npm test
 */
import { METHOD_ORDER } from '@/lib/evidence/order'

export type MethodGroupId = 'strength' | 'ndt' | 'inspection' | 'reinforcement' | 'documents' | 'other'

export const METHOD_GROUPS: { id: MethodGroupId; title: string; hint: string; methods: string[] }[] = [
  { id: 'strength', title: 'Strength', hint: 'Samples tested in a laboratory', methods: ['core_compression'] },
  { id: 'ndt', title: 'Non-destructive', hint: 'Measured on the piece, nothing damaged', methods: ['rebound_hammer'] },
  { id: 'inspection', title: 'Inspection', hint: 'What is seen on the piece', methods: ['visual_inspection'] },
  { id: 'reinforcement', title: 'Reinforcement', hint: 'Where the bars lie', methods: ['reinforcement_layout'] },
  {
    id: 'documents',
    title: 'Documents and claims',
    hint: 'What a source says about the piece',
    methods: ['archival_document', 'manufacturer_datasheet', 'era_heuristic'],
  },
]

type Named = { name: string; label?: string; description?: string }

export type MethodGroup<T extends Named> = { id: MethodGroupId; title: string; hint: string; methods: T[] }

/** The methods in their groups, a group without a method left out; a method of no group goes to `other`. */
export function groupMethods<T extends Named>(methods: T[]): MethodGroup<T>[] {
  const known = new Set(METHOD_GROUPS.flatMap((g) => g.methods))
  const rank = (name: string) => {
    const index = METHOD_ORDER.indexOf(name)
    return index === -1 ? METHOD_ORDER.length : index
  }
  const groups: MethodGroup<T>[] = METHOD_GROUPS.map((group) => ({
    id: group.id,
    title: group.title,
    hint: group.hint,
    methods: group.methods
      .map((name) => methods.find((m) => m.name === name))
      .filter((m): m is T => m !== undefined)
      .sort((a, b) => rank(a.name) - rank(b.name)),
  })).filter((group) => group.methods.length > 0)
  const rest = methods.filter((m) => !known.has(m.name))
  if (rest.length > 0) groups.push({ id: 'other', title: 'Other', hint: '', methods: rest })
  return groups
}

const lower = (text: string | undefined) => (text ?? '').toLowerCase()

/** The methods whose name, label, description or group title contain every word of the query. */
export function searchMethods<T extends Named>(methods: T[], query: string): T[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return methods
  const groupOf = (name: string) => METHOD_GROUPS.find((g) => g.methods.includes(name))
  return methods.filter((method) => {
    const group = groupOf(method.name)
    const haystack = [
      lower(method.name).replace(/_/g, ' '), lower(method.label), lower(method.description),
      lower(group?.title), lower(group?.hint),
    ].join(' ')
    return words.every((word) => haystack.includes(word))
  })
}
