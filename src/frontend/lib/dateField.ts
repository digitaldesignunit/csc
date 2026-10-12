/**
 * The text of a date as the shared `DateField` takes it (decision 8.143):
 * `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, as far as the field's precision allows.
 * Pure functions: the component only edits and shows what these return.
 *
 * Run: npm test
 */

export type DatePrecision = 'year' | 'month' | 'day'

export const FIRST_YEAR = 1900

/** The last year a date may name: next year (planned work, 8.104). */
export const lastYear = (now: Date = new Date()): number => now.getFullYear() + 1

export type DateParse =
  | { kind: 'empty' }
  /** A valid start of a date that is not complete yet (typing in progress). */
  | { kind: 'partial' }
  | { kind: 'ok'; text: string; precision: DatePrecision; year: number; month: number; day: number }
  | { kind: 'error'; message: string }

const pad = (n: number, width = 2) => String(n).padStart(width, '0')

const ORDER: DatePrecision[] = ['year', 'month', 'day']

/** `YYYY`, `YYYY-MM` or `YYYY-MM-DD` of the precisions a field allows. */
export function formatHint(allowed: DatePrecision[]): string {
  const forms = ORDER.filter((p) => allowed.includes(p)).map((p) =>
    (p === 'year' ? 'YYYY' : p === 'month' ? 'YYYY-MM' : 'YYYY-MM-DD'))
  if (forms.length === 0) return 'YYYY-MM-DD'
  if (forms.length === 1) return forms[0]
  return `${forms.slice(0, -1).join(', ')} or ${forms[forms.length - 1]}`
}

export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate()
}

/** The canonical text of a date at a precision (`2024`, `2024-05`, `2024-05-03`). */
export function canonical(year: number, month: number, day: number, precision: DatePrecision): string {
  if (precision === 'year') return pad(year, 4)
  if (precision === 'month') return `${pad(year, 4)}-${pad(month)}`
  return `${pad(year, 4)}-${pad(month)}-${pad(day)}`
}

/** Which precision a canonical text has; null when it is none. */
export function precisionOf(text: string): DatePrecision | null {
  if (/^\d{4}$/.test(text)) return 'year'
  if (/^\d{4}-\d{2}$/.test(text)) return 'month'
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return 'day'
  return null
}

/** The text cut to a precision (`2024-05-03` to `2024-05`); a coarser text stays. */
export function truncateTo(text: string, precision: DatePrecision): string {
  const have = precisionOf(text)
  if (!have) return text
  if (ORDER.indexOf(have) <= ORDER.indexOf(precision)) return text
  return text.slice(0, precision === 'year' ? 4 : 7)
}

/** The first day of the period as `YYYY-MM-DD` (what an ISO field stores). */
export function firstDay(text: string): string {
  const have = precisionOf(text)
  if (have === 'year') return `${text}-01-01`
  if (have === 'month') return `${text}-01`
  return text
}

type Pieces = { year: number; month: number | null; day: number | null }

/** Splits a typed text into numbers: ISO order or the German `D.M.YYYY`. */
function pieces(text: string): Pieces | 'partial' | null {
  let match = /^(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?$/.exec(text)
  if (match) {
    // a single 0 is the first digit of a month or day: typing goes on
    if (match[2] === '0' || match[3] === '0') return 'partial'
    return {
      year: Number(match[1]),
      month: match[2] !== undefined ? Number(match[2]) : null,
      day: match[3] !== undefined ? Number(match[3]) : null,
    }
  }
  match = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(text)
  if (match) return { year: Number(match[3]), month: Number(match[2]), day: Number(match[1]) }
  match = /^(\d{1,2})\.(\d{4})$/.exec(text)
  if (match) return { year: Number(match[2]), month: Number(match[1]), day: null }
  // the start of a date: up to three digits, a year and a separator, the first digit of a part
  if (/^\d{1,3}$/.test(text) || /^\d{4}[-/.]\d{0,2}$/.test(text) || /^\d{4}[-/.]\d{1,2}[-/.]\d{0,2}$/.test(text)) {
    return 'partial'
  }
  return null
}

/**
 * Reads a typed date. `allowed` are the precisions the field takes (default:
 * a full day); a shorter text than the field allows is `partial` (the user
 * may be typing on), reported as an error only when the field is left.
 */
export function parseDate(
  input: string,
  allowed: DatePrecision[] = ['day'],
  now: Date = new Date(),
): DateParse {
  const text = input.trim()
  if (text === '') return { kind: 'empty' }
  const hint = formatHint(allowed)
  const got = pieces(text)
  if (got === null) return { kind: 'error', message: `Write the date as ${hint}.` }
  if (got === 'partial') return { kind: 'partial' }

  const max = lastYear(now)
  if (got.year < FIRST_YEAR || got.year > max) {
    return { kind: 'error', message: `The year is between ${FIRST_YEAR} and ${max}.` }
  }
  if (got.month !== null && (got.month < 1 || got.month > 12)) {
    return { kind: 'error', message: `${got.month} is not a month (1 to 12).` }
  }
  if (got.day !== null && got.month !== null) {
    const days = daysInMonth(got.year, got.month)
    if (got.day < 1 || got.day > days) {
      return {
        kind: 'error',
        message: `${canonical(got.year, got.month, 1, 'month')} has ${days} days.`,
      }
    }
  }
  const precision: DatePrecision = got.day !== null ? 'day' : got.month !== null ? 'month' : 'year'
  if (!allowed.includes(precision)) {
    // a shorter text than the field takes may still be typed on; a longer one is an error
    const longer = allowed.some((a) => ORDER.indexOf(a) > ORDER.indexOf(precision))
    return longer ? { kind: 'partial' } : { kind: 'error', message: `This field takes ${hint}.` }
  }
  const month = got.month ?? 1
  const day = got.day ?? 1
  return { kind: 'ok', text: canonical(got.year, month, day, precision), precision, year: got.year, month, day }
}

/** A message for a text left as it is: a partial date is not a date. */
export function finalMessage(input: string, allowed: DatePrecision[] = ['day'], now: Date = new Date()): string | null {
  const result = parseDate(input, allowed, now)
  if (result.kind === 'error') return result.message
  if (result.kind === 'partial') return `Finish the date: ${formatHint(allowed)}.`
  return null
}

/** The local `Date` of a parsed date (the first day of its period). */
export function toLocalDate(result: Extract<DateParse, { kind: 'ok' }>): Date {
  return new Date(result.year, result.month - 1, result.day)
}

/** Today at a precision, in the browser's own time zone. */
export function todayText(precision: DatePrecision = 'day', now: Date = new Date()): string {
  return canonical(now.getFullYear(), now.getMonth() + 1, now.getDate(), precision)
}

/** The years of one page of the year grid (12 per page, the first page holds `year`). */
export function yearPage(year: number, now: Date = new Date()): { first: number; years: number[] } {
  const max = lastYear(now)
  const top = Math.min(max, Math.max(FIRST_YEAR + 11, year + 5))
  const first = Math.max(FIRST_YEAR, top - 11)
  const years: number[] = []
  for (let y = first; y < first + 12 && y <= max; y += 1) years.push(y)
  return { first, years }
}
