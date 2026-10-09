/**
 * The order of the method cards in the evidence form (plan P11 stage 3,
 * decision 8.118 S5): by use on site, the two common methods first. A method
 * the list does not know goes last, in the order the backend gave.
 */
export const METHOD_ORDER = [
  'visual_inspection',
  'rebound_hammer',
  'reinforcement_layout',
  'archival_document',
  'manufacturer_datasheet',
  'era_heuristic',
  'core_compression',
]

export function orderMethods<T extends { name: string }>(methods: T[]): T[] {
  const rank = (name: string) => {
    const index = METHOD_ORDER.indexOf(name)
    return index === -1 ? METHOD_ORDER.length : index
  }
  return methods
    .map((method, position) => ({ method, position }))
    .sort((a, b) => rank(a.method.name) - rank(b.method.name) || a.position - b.position)
    .map(({ method }) => method)
}

/** The tier as a short chip on a method card: the full label would repeat the method's name. */
export const TIER_CHIP_LABELS: Record<string, string> = {
  destructive: 'Destructive',
  ndt: 'Non-destructive',
  archival: 'Archival',
  visual: 'Visual',
  heuristic: 'Estimate',
}

export function tierChip(tier: string | null | undefined, fromPayload?: boolean | null): string {
  if (fromPayload) return 'Source varies'
  return (tier && TIER_CHIP_LABELS[tier]) || ''
}
