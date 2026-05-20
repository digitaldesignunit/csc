import { format, isValid, parseISO } from 'date-fns'

/** Parse ``YYYY-MM-DD`` (or ISO prefix) to a local Date. */
export function parseYyyyMmDd(value: string): Date | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const d = parseISO(trimmed.length >= 10 ? trimmed.slice(0, 10) : trimmed)
  return isValid(d) ? d : undefined
}

export function formatYyyyMmDd(date: Date | undefined): string {
  if (!date || !isValid(date)) return ''
  return format(date, 'yyyy-MM-dd')
}
