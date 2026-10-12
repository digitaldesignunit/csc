/**
 * The facts of one record in the records table (decision 8.134 d) and of one
 * bar in the bars table (8.134 h): what a row shows before it is opened.
 *
 * Run: npm test
 */
import type { PositionState, RecordState } from '@/components/evidence/form/state'
import { barIssues } from '@/lib/evidence/issues'
import { layoutOf } from '@/lib/evidence/layout'
import { getAt, isBlank, isObject, parseNumber, setAt, type FormObject } from '@/lib/evidence/schema'

export type RecordRow = {
  title: string
  /** where on the piece, in words */
  where: string
  facts: string[]
}

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '')

/** The grid of a rebound test area, `3 x 3`, or null. */
function gridWords(payload: FormObject): string | null {
  const grid = getAt(payload, ['test_area', 'grid'])
  if (!isObject(grid)) return null
  const rows = parseNumber(String((grid as FormObject).rows ?? ''))
  const cols = parseNumber(String((grid as FormObject).cols ?? ''))
  return rows && cols ? `${rows} x ${cols} grid` : null
}

export function whereWords(position: PositionState, payload: FormObject): string {
  const words = position.description.trim()
  if (words) return words
  const grid = gridWords(payload)
  if (grid) return grid
  if (position.kind === 'point' && position.point) return 'point picked on the model'
  return ''
}

/** Entered, rejected and valid readings of a rebound record. */
export function readingCounts(payload: FormObject): { entered: number; rejected: number; valid: number } {
  const readings = Array.isArray(payload.readings) ? payload.readings : []
  const rejected = Array.isArray(payload.rejected_reading_indices)
    ? new Set(payload.rejected_reading_indices.map(Number).filter((n) => Number.isInteger(n) && n < readings.length)).size
    : 0
  return { entered: readings.length, rejected, valid: readings.length - rejected }
}

export function recordRow(method: string, record: RecordState, index: number): RecordRow {
  const layout = layoutOf(method)
  const label = layout.labelPath ? text(getAt(record.payload, layout.labelPath.split('.'))) : ''
  const facts: string[] = []
  if (method === 'rebound_hammer') {
    const { entered, rejected, valid } = readingCounts(record.payload)
    facts.push(entered === 0 ? 'no readings' : `${valid} valid reading${valid === 1 ? '' : 's'}`
      + (rejected ? `, ${rejected} rejected` : ''))
  } else if (method === 'core_compression') {
    const cored = text(getAt(record.payload, ['sampling', 'cored_at']))
    const diameter = text(getAt(record.payload, ['specimen', 'measured_diameter_mm']))
    if (cored) facts.push(`cored ${cored}`)
    if (diameter) facts.push(`diameter ${diameter} mm`)
    const load = text(getAt(record.payload, ['test', 'max_load_kn']))
    if (load) facts.push(`${load} kN`)
    if (facts.length === 0) facts.push('not filled in yet')
  }
  if (record.derived.model) facts.push('derived result')
  return {
    title: label || `${layout.recordLabel.charAt(0).toUpperCase()}${layout.recordLabel.slice(1)} ${index + 1}`,
    where: whereWords(record.position, record.payload),
    facts,
  }
}

// BARS ------------------------------------------------------------------------
export type BarRow = {
  title: string
  diameter: string
  grade: string
  cover: string
  points: number
  problems: string[]
}

export function barRow(bar: FormObject, index: number): BarRow {
  const points = Array.isArray(bar.points) ? bar.points.filter((p) => !isBlank(p)).length : 0
  const diameter = text(bar.diameter_mm)
  return {
    title: `Bar ${index + 1}`,
    diameter: diameter ? `${diameter} mm` : '',
    grade: text(bar.spec),
    cover: text(bar.cover_mm) ? `${text(bar.cover_mm)} mm` : '',
    points,
    problems: barIssues(bar),
  }
}

/** The bars with a field set on the selected ones (bulk diameter or grade, 8.134 h). */
export function setOnBars(bars: FormObject[], selected: ReadonlySet<number>, field: 'diameter_mm' | 'spec', value: string): FormObject[] {
  return bars.map((bar, index) => (selected.has(index) ? (setAt(bar, [field], value) as FormObject) : bar))
}

/** The bars without the selected ones. */
export function removeBars(bars: FormObject[], selected: ReadonlySet<number>): FormObject[] {
  return bars.filter((_, index) => !selected.has(index))
}

/** The indices of the bars that have a problem. */
export function barsWithProblems(bars: FormObject[]): number[] {
  return bars.map((bar, index) => (barIssues(bar).length > 0 ? index : -1)).filter((i) => i >= 0)
}

/** One point per line, `x y z`, as the points of a bar. */
export function parsePointsText(textValue: string): string[][] {
  return textValue
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/[\s,;]+/).filter(Boolean))
}
