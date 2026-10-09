/**
 * Display helpers for evidence results, folded properties and the
 * condition badge (spec sections 4.4, 2.6; decision 7.9). No rules of the
 * data model live here: the fold is the backend's, this only shows it.
 */
import { QUANTITY_LABELS, SOURCE_TIER_LABELS, vocabLabel } from '@/generated/Vocab'

export type FoldedProperty = {
  range?: (number | string)[] | null
  unit?: string | null
  confidence?: number | null
  source?: string | null
  n?: number | null
  evidence_ids?: string[] | null
  inherited_from?: string[] | null
}

/** Findings that are severities 0 (none) to 3 (severe) (decision 7.9). */
export const FINDING_QUANTITIES = ['spalling', 'cracking', 'corrosion'] as const

export function quantityLabel(name: string): string {
  return vocabLabel(QUANTITY_LABELS, name)
}

export function tierLabel(tier: string | null | undefined): string {
  return tier ? vocabLabel(SOURCE_TIER_LABELS, tier) : ''
}

function shownNumber(value: number): string {
  if (Number.isInteger(value)) return String(value)
  return String(Math.round(value * 1000) / 1000)
}

function shownItem(value: number | string): string {
  return typeof value === 'number' ? shownNumber(value) : String(value)
}

/** "18 - 28 MPa", "B225", "43"; classes and categories joined by comma. */
export function formatRange(range: (number | string)[] | null | undefined, unit?: string | null): string {
  if (!range || range.length === 0) return '---'
  const numeric = range.length === 2 && range.every((v) => typeof v === 'number')
  let text: string
  if (numeric) {
    const [lo, hi] = range as number[]
    text = lo === hi ? shownNumber(lo) : `${shownNumber(lo)} - ${shownNumber(hi)}`
  } else {
    text = range.map(shownItem).join(', ')
  }
  return unit && unit !== '1' ? `${text} ${unit}` : text
}

type ResultLike = {
  value?: number | string | null
  range?: (number | string)[] | null
  unit?: string | null
}

/** A summary or derived result as text. */
export function formatResult(result: ResultLike | null | undefined): string {
  if (!result) return 'a document'                    // no result: a document (8.106)
  if (result.value !== undefined && result.value !== null && result.value !== '') {
    const text = shownItem(result.value)
    const unit = result.unit && result.unit !== '1' ? ` ${result.unit}` : ''
    if (result.range && result.range.length) {
      return `${text}${unit} (${formatRange(result.range, null)})`
    }
    return `${text}${unit}`
  }
  return formatRange(result.range, result.unit)
}

export function formatConfidence(confidence: number | null | undefined): string {
  return typeof confidence === 'number' ? `${Math.round(confidence * 100)} %` : ''
}

export type ConditionBadge = {
  grade: number | null
  /** where the number comes from, or why there is none */
  basis: 'grade' | 'findings' | 'none'
}

function numericRange(property: FoldedProperty | undefined): [number, number] | null {
  const range = property?.range
  if (!range || range.length === 0) return null
  const numbers = range.filter((v): v is number => typeof v === 'number')
  if (numbers.length === 0) return null
  return [Math.min(...numbers), Math.max(...numbers)]
}

/**
 * Decision 7.9: the folded `condition_grade`, else 3 minus the worst
 * finding severity, else "not assessed". A grade range shows its worst
 * (lowest) end, a finding range its worst (highest) end.
 */
export function conditionBadge(properties: Record<string, unknown> | null | undefined): ConditionBadge {
  const props = (properties ?? {}) as Record<string, FoldedProperty | undefined>
  const grade = numericRange(props.condition_grade)
  if (grade) return { grade: grade[0], basis: 'grade' }
  const severities = FINDING_QUANTITIES
    .map((name) => numericRange(props[name]))
    .filter((r): r is [number, number] => r !== null)
    .map((r) => r[1])
  if (severities.length) {
    return { grade: Math.max(0, Math.min(3, 3 - Math.max(...severities))), basis: 'findings' }
  }
  return { grade: null, basis: 'none' }
}

export const VERIFICATION_NOTES: Record<string, string> = {
  unverified: 'Nobody has confirmed this record.',
  self_attested: 'The recorder stands by the result.',
  reviewed: 'A second person reviewed the record.',
  accredited: 'Reviewed; the laboratory holds an accreditation covering the standard.',
}

export function verificationClass(state: string | null | undefined): string {
  switch (state) {
    case 'accredited':
      return 'border-green-500 text-green-800 dark:text-green-300'
    case 'reviewed':
      return 'border-emerald-500 text-emerald-800 dark:text-emerald-300'
    case 'self_attested':
      return 'border-sky-500 text-sky-800 dark:text-sky-300'
    default:
      return 'border-border text-muted-foreground'
  }
}

export function statusClass(status: string | null | undefined): string {
  switch (status) {
    case 'published':
      return ''
    case 'rejected':
    case 'withdrawn':
      return 'border-red-400 text-red-800 dark:text-red-200'
    default:
      return 'border-amber-400 text-amber-800 dark:text-amber-200'
  }
}
