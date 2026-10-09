/**
 * The instant the evidence form sends for the date of an observation
 * (decision 8.91 b): a date that is today is *now*, to the minute, so that a
 * same-day inspection falls on the state recorded earlier that day; a past
 * date stays the day-precise UTC midnight, which the context resolution of
 * spec 4.1 reads as its midnight (unchanged).
 */

export type ObservationInstant = {
  observed_at: string
  observed_at_precision: 'exact' | 'day'
}

const pad = (n: number) => String(n).padStart(2, '0')

/** `YYYY-MM-DD` of a moment in the browser's own time zone. */
export function localDay(now: Date): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/** A date typed in the form (`YYYY-MM-DD`) as the instant sent to the server. */
export function observationInstant(date: string, now: Date = new Date()): ObservationInstant | null {
  const day = date.trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null
  if (day === localDay(now)) {
    const minute = new Date(Math.floor(now.getTime() / 60_000) * 60_000)
    return { observed_at: minute.toISOString().replace(/\.\d{3}Z$/, 'Z'), observed_at_precision: 'exact' }
  }
  return { observed_at: `${day}T00:00:00Z`, observed_at_precision: 'day' }
}
