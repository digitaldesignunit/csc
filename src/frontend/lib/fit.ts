/**
 * The "Fits" search of Browse (decision 8.169, 8.173): which pieces are about
 * a size, and which can hold a size. The state is three URL parameters that
 * the backend list and count take unchanged: `fit_mode` (about | can_hold),
 * `fit_size` (three sizes in mm, any order) and `fit_tol` (about only: "10%"
 * or "50mm"). The parts that read and build them, and the words for a row's
 * match, are pure and tested; the filter bar and the table only call them.
 */
import type { ParamsLike } from '@/lib/browse'
import type { CatalogRow } from '@/generated/CatalogModels'
import { parseNear } from '@/lib/near'

export const FIT_MODES = ['about', 'can_hold'] as const
export type FitMode = (typeof FIT_MODES)[number]

export const FIT_KEYS = ['fit_mode', 'fit_size', 'fit_tol'] as const
export const DEFAULT_TOLERANCE = '10%'
export const MAX_FIT_MM = 100_000

export const FIT_MODE_LABELS: Record<FitMode, string> = {
  about: 'About this size',
  can_hold: 'Can hold this size',
}

export const FIT_HELP =
  'Enter the size of the part you look for, in mm, in any order. About this size lists elements whose '
  + 'three sides are each within the tolerance of yours. Can hold this size lists elements you could cut '
  + 'that part from: every side of the element is at least as long as yours (the part may be turned). '
  + 'The sides are compared largest to smallest, so the way an element lies does not matter.'

export type FitQuery = {
  mode: FitMode
  /** The three asked sides in mm, as typed. */
  size: [number, number, number]
  /** Only for `about`: "10%" or "50mm". */
  tolerance: string | null
}

/** A fit as the backend sends it with a row. */
export type FitMatch =
  | { mode: 'about'; deviation: number }
  | { mode: 'can_hold'; waste_mm3: number; waste_percent: number }

const NUMBER = /^\d+(?:\.\d+)?$/
const TOLERANCE = /^(\d+(?:\.\d+)?)\s*(%|mm)$/i

/** "1200,600,200" -> three sizes above 0 and at most 100 m, else null. */
export function parseFitSize(text: string | null | undefined): [number, number, number] | null {
  const parts = (text ?? '').split(',').map((p) => p.trim())
  if (parts.length !== 3 || !parts.every((p) => NUMBER.test(p))) return null
  const sides = parts.map(Number)
  if (!sides.every((s) => s > 0 && s <= MAX_FIT_MM)) return null
  return sides as [number, number, number]
}

/** "10%" or "50mm" (any case, spaces allowed) -> the normal text, else null. */
export function parseFitTolerance(text: string | null | undefined): string | null {
  const found = TOLERANCE.exec((text ?? '').trim())
  if (!found) return null
  const value = Number(found[1])
  const unit = found[2].toLowerCase()
  if (unit === '%' ? value > 100 : value > MAX_FIT_MM) return null
  return `${found[1]}${unit}`
}

/** The fit of the URL, or null when there is none or it cannot be used (then
 *  it is ignored, not sent: the backend would answer 422). */
export function parseFit(params: ParamsLike): FitQuery | null {
  const mode = params.get('fit_mode')
  if (!(FIT_MODES as readonly string[]).includes(mode ?? '')) return null
  const size = parseFitSize(params.get('fit_size'))
  if (!size) return null
  if (mode === 'can_hold') return { mode, size, tolerance: null }
  const tolerance = parseFitTolerance(params.get('fit_tol')) ?? DEFAULT_TOLERANCE
  return { mode: 'about', size, tolerance }
}

/** The parameters for the backend list and count (empty without a usable fit). */
export function fitBackendParams(params: ParamsLike): Record<string, string> {
  const fit = parseFit(params)
  if (!fit) return {}
  return {
    fit_mode: fit.mode,
    fit_size: fit.size.join(','),
    ...(fit.tolerance ? { fit_tol: fit.tolerance } : {}),
  }
}

/** The URL changes that set a fit (null values remove): the default tolerance
 *  is not written, `can_hold` carries none. `wasActive` says whether a fit was
 *  already in the URL: a fit that starts or ends also resets the sort, so an
 *  earlier explicit sort does not beat the match of a fresh fit and `match`
 *  never outlives its fit. Changing a fit that is active keeps the sort. */
export function fitChanges(fit: FitQuery | null, wasActive = false): Record<string, string | null> {
  const sort: Record<string, null> = !fit || !wasActive ? { sortkey: null, sortorder: null } : {}
  if (!fit) return { fit_mode: null, fit_size: null, fit_tol: null, ...sort }
  return {
    ...sort,
    fit_mode: fit.mode,
    fit_size: fit.size.join(','),
    fit_tol: fit.mode === 'about' && fit.tolerance && fit.tolerance !== DEFAULT_TOLERANCE ? fit.tolerance : null,
  }
}

/** "1200 x 600 x 200 mm", largest first. */
export function fitSizeText(size: readonly number[]): string {
  return `${[...size].sort((a, b) => b - a).join(' x ')} mm`
}

/** The chip of an active fit: "About 1200 x 600 x 200 mm (10 %)". */
export function fitChipLabel(fit: FitQuery): string {
  if (fit.mode === 'can_hold') return `Can hold ${fitSizeText(fit.size)}`
  return `About ${fitSizeText(fit.size)} (${(fit.tolerance ?? DEFAULT_TOLERANCE).replace('%', ' %').replace('mm', ' mm')})`
}

/** The sort a list has while no other is asked: the distance under a near
 *  search (also with a fit: the fit filters, the distance sorts, 8.173), else
 *  the match under a fit. */
export function defaultSortKey(params: ParamsLike): string {
  if (parseNear(params)) return 'distance'
  return parseFit(params) ? 'match' : '_id'
}

// A ROW'S MATCH -----------------------------------------------------------------
/** The `fit` of a list row (the generated `CatalogRow.fit`), or null: a list
 *  without a dimension search carries none. The generated union does not keep
 *  the literal `mode`, so the two shapes are told apart by their value. */
export function rowFit(row: Pick<CatalogRow, 'fit'> | null | undefined): FitMatch | null {
  const fit = row?.fit
  if (!fit) return null
  if ('deviation' in fit && typeof fit.deviation === 'number') return { mode: 'about', deviation: fit.deviation }
  if ('waste_mm3' in fit && typeof fit.waste_mm3 === 'number' && typeof fit.waste_percent === 'number') {
    return { mode: 'can_hold', waste_mm3: fit.waste_mm3, waste_percent: fit.waste_percent }
  }
  return null
}

/** "8.3 % off", or "exact" when the sides agree (to 0.05 %). */
export function deviationText(ratio: number): string {
  const percent = ratio * 100
  if (percent < 0.05) return 'exact'
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)} % off`
}

/** A volume in mm3 as m3 with two significant digits, never in an exponent:
 *  "0.0017 m3", "0.12 m3", "1.5 m3", "12 m3". */
export function volumeText(mm3: number): string {
  const rounded = Number((mm3 / 1e9).toPrecision(2))
  if (rounded === 0) return '0 m3'
  const decimals = Math.min(12, Math.max(0, 1 - Math.floor(Math.log10(rounded))))
  const text = rounded.toFixed(decimals)
  return `${decimals > 0 ? text.replace(/0+$/, '').replace(/\.$/, '') : text} m3`
}

/** The waste as a share of the piece's box volume, whole per cent: "41 %", "<1 %".
 *  Never "100 %" unless the waste is exactly 100 %: 99.97 % shows as "99 %" (a
 *  "100 %" reads as nothing usable, decision 8.169). */
export function percentText(percent: number): string {
  if (percent < 1) return '<1 %'
  return `${percent < 100 ? Math.min(99, Math.round(percent)) : 100} %`
}

/** "no waste", or "41 % waste (0.12 m3)"; "... per piece" for a batch (the size is one piece's). */
export function wasteText(mm3: number, percent: number, quantity = 1): string {
  if (mm3 < 500) return 'no waste'
  return `${percentText(percent)} waste (${volumeText(mm3)})${quantity > 1 ? ' per element' : ''}`
}

/** The match of a row on two lines for a narrow table cell: the share
 *  ("41 % waste") over the volume ("0.12 m3", "0.12 m3 per piece" for a batch).
 *  The about text and "no waste" are one line. */
export function fitRowLines(fit: FitMatch | null, quantity = 1): string[] {
  if (!fit) return []
  if (fit.mode === 'about') return [deviationText(fit.deviation)]
  if (fit.waste_mm3 < 500) return ['no waste']
  return [`${percentText(fit.waste_percent)} waste`, `${volumeText(fit.waste_mm3)}${quantity > 1 ? ' per element' : ''}`]
}

/** What a row says about its match: "8.3 % off", "41 % waste (0.12 m3)", or nothing. */
export function fitRowText(fit: FitMatch | null, quantity = 1): string {
  if (!fit) return ''
  return fit.mode === 'about' ? deviationText(fit.deviation) : wasteText(fit.waste_mm3, fit.waste_percent, quantity)
}
