/**
 * The pure parts of Analytics (plan P11 stage 2, decision 8.118 C-3): the
 * query of the shared filter bar, the one line that replaces the tiles, the
 * labels of the charts.
 */
import { ORIGINAL_FUNCTION_LABELS, vocabLabel } from '@/generated/Vocab'
import { FILTER_KEYS, type ParamsLike } from '@/lib/browse'

export type DistItem = { label: string; count: number }

export type StatsResponse = {
  total: number
  /** the pieces the current states stand for (a batch counts its quantity) */
  pieces?: number
  byOriginalFunction: DistItem[]
  byShapeClass: DistItem[]
  byMaterial: DistItem[]
  byDataset: DistItem[]
  byComplexity: DistItem[]
  byStatus: DistItem[]
  byFragment: DistItem[]
  byCirculation?: DistItem[]
  reserved: DistItem[]
  descriptorsKeys: DistItem[]
  createdMonthly: DistItem[]
  bbxX: DistItem[]
}

export const EMPTY_STATS: StatsResponse = {
  total: 0,
  pieces: 0,
  byOriginalFunction: [],
  byShapeClass: [],
  byMaterial: [],
  byDataset: [],
  byComplexity: [],
  byStatus: [],
  byFragment: [],
  byCirculation: [],
  reserved: [],
  descriptorsKeys: [],
  createdMonthly: [],
  bbxX: [],
}

/** The stats request for the URL's filters: every circulation, so the
 *  Circulation chart can show where the pieces are, and a Top-N wide enough to
 *  count the datasets. */
export function statsQuery(params: ParamsLike): string {
  const query = new URLSearchParams()
  for (const key of FILTER_KEYS) {
    const value = params.get(key)
    if (value) query.set(key, value)
  }
  query.set('circulation', 'all')
  query.set('limit_dim', '1000')
  return query.toString()
}

/** "655 components in 7 datasets, 1,011 pieces": one line instead of the tiles. */
export function summaryLine(stats: StatsResponse): string {
  const datasets = stats.byDataset.filter((d) => d.label !== 'others').length
  const plural = (n: number, one: string, many: string) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`
  const parts = [`${plural(stats.total, 'component', 'components')} in ${plural(datasets, 'dataset', 'datasets')}`]
  if (stats.pieces != null && stats.pieces > stats.total) {
    parts.push(plural(stats.pieces, 'piece', 'pieces'))
  }
  return parts.join(', ')
}

const CIRCULATION_LABELS: Record<string, string> = {
  in_place: 'In place',
  deinstalled: 'Not in place',
  exited: 'Out of circulation',
}
/** The order of the circulation chart: where a piece is, then where it left. */
const CIRCULATION_ORDER = ['in_place', 'deinstalled', 'exited']

export function circulationItems(items: DistItem[] | undefined): DistItem[] {
  const byLabel = new Map((items ?? []).map((i) => [i.label, i.count]))
  return CIRCULATION_ORDER.filter((key) => byLabel.has(key)).map((key) => ({
    label: CIRCULATION_LABELS[key],
    count: byLabel.get(key) ?? 0,
  }))
}

export function functionItems(items: DistItem[] | undefined): DistItem[] {
  return (items ?? []).map((d) => ({ ...d, label: vocabLabel(ORIGINAL_FUNCTION_LABELS, d.label) }))
}

export function materialItems(items: DistItem[] | undefined, label: (id: string) => string): DistItem[] {
  return (items ?? []).map((d) => ({ ...d, label: d.label === 'others' || d.label === 'unknown' ? d.label : label(d.label) }))
}

/** The first n values (they come most frequent first), the rest summed as "others". */
export function topN(items: DistItem[] | undefined, n = 10): DistItem[] {
  const rows = items ?? []
  const named = rows.filter((d) => d.label !== 'others')
  const extra = rows.filter((d) => d.label === 'others').reduce((sum, d) => sum + d.count, 0)
  const head = named.slice(0, n)
  const rest = named.slice(n).reduce((sum, d) => sum + d.count, 0) + extra
  return rest > 0 ? [...head, { label: 'others', count: rest }] : head
}
