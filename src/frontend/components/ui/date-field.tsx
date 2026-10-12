'use client'

/**
 * The one date field of the app (decision 8.143): typing first (`YYYY`,
 * `YYYY-MM` or `YYYY-MM-DD` as far as the field's precision allows, with an
 * inline message), and a calendar popover with month and year dropdowns, a
 * year grid and a month grid one click away, "Today" and "Clear". A field
 * that takes more than a day shows a precision choice (year / month / day)
 * next to it; year precision opens the year grid. The value is the canonical
 * text (`''`, `2024`, `2024-05`, `2024-05-03`); `lib/dateField.ts` reads and
 * formats it.
 *
 * Alignment: the control has the height of the other inputs; label, help and
 * error layout are the caller's (`Field` of the evidence form, the lineage
 * `Field`), or `label` here for a field without one.
 */
import { useEffect, useRef, useState } from 'react'
import { CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  FIRST_YEAR,
  finalMessage,
  formatHint,
  lastYear,
  parseDate,
  precisionOf,
  todayText,
  toLocalDate,
  truncateTo,
  yearPage,
  type DatePrecision,
} from '@/lib/dateField'
import { cn } from '@/lib/utils'

const ORDER: DatePrecision[] = ['year', 'month', 'day']
const PRECISION_NAMES: Record<DatePrecision, string> = { year: 'Year', month: 'Month', day: 'Day' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

type View = 'days' | 'months' | 'years'

export type DateFieldProps = {
  id: string
  /** The canonical text: empty, `2024`, `2024-05` or `2024-05-03`. */
  value: string
  /** The new text and the precision it is given at (callers that keep none ignore it). */
  onChange: (value: string, precision: DatePrecision) => void
  /** What the field takes (default: a full day). */
  precisions?: DatePrecision[]
  /**
   * The precision the field is known to (`at_precision`), kept by the
   * caller: the shown text follows it, and `onChange` reports a typed or
   * chosen precision as its second argument.
   */
  precision?: DatePrecision
  /** Show the precision choice (default: when the field takes more than one). */
  showPrecision?: boolean
  label?: string
  disabled?: boolean
  required?: boolean
  /** An error of the caller (the server's), shown with the field's own. */
  error?: string
  className?: string
}

function startView(mode: DatePrecision): View {
  return mode === 'year' ? 'years' : mode === 'month' ? 'months' : 'days'
}

function coarsest(precisions: DatePrecision[]): DatePrecision {
  return ORDER.filter((p) => precisions.includes(p)).pop() ?? 'day'
}

export function DateField({
  id,
  value,
  onChange,
  precisions = ['day'],
  precision,
  showPrecision,
  label,
  disabled,
  required,
  error,
  className,
}: DateFieldProps) {
  const allowed = ORDER.filter((p) => precisions.includes(p))
  const hasChoice = (showPrecision ?? allowed.length > 1) && allowed.length > 1
  // the mode: the precision the field is given at (from the text, else the caller's or the finest)
  const [ownMode, setOwnMode] = useState<DatePrecision>(() => precisionOf(value) ?? coarsest(allowed))
  const mode: DatePrecision = precision ?? ownMode

  const shown = (v: string) => (precision ? truncateTo(v, precision) : v)
  const [text, setText] = useState(shown(value))
  const [touched, setTouched] = useState(false)
  const lastSent = useRef(value)
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<View>(startView(mode))
  const [cursor, setCursor] = useState<Date>(() => new Date())

  // follow a change of the value that the field did not make itself
  useEffect(() => {
    if (value !== lastSent.current) {
      lastSent.current = value
      setText(shown(value))
      const have = precisionOf(value)
      if (have && !precision) setOwnMode(have)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  // the shown text follows a change of the given precision
  useEffect(() => {
    if (precision) setText((prev) => truncateTo(prev, precision))
  }, [precision])

  /** Tell the caller; `given` is the precision the text is given at. */
  const emit = (next: string, given: DatePrecision = mode) => {
    lastSent.current = next
    if (precision === undefined) setOwnMode(given)
    onChange(next, given)
  }

  const parsed = parseDate(text, allowed)
  const inline = parsed.kind === 'error'
    ? parsed.message
    : touched ? finalMessage(text, allowed) : null
  const message = inline ?? error ?? null

  const onType = (next: string) => {
    setText(next)
    const result = parseDate(next, allowed)
    if (result.kind === 'ok') {
      emit(result.text, result.precision)
    } else if (result.kind === 'empty' || lastSent.current !== '') {
      emit('')                    // not a date (yet): the field holds nothing, never an old value
    }
  }

  const pick = (next: string) => {
    setText(next)
    setTouched(true)
    emit(next, precisionOf(next) ?? mode)
    setOpen(false)
  }

  const changePrecision = (next: DatePrecision) => {
    const cut = truncateTo(value, next)
    setText(cut)
    emit(cut, next)
    setView(startView(next))
    setOpen(true)
  }

  const onOpenChange = (next: boolean) => {
    if (next) {
      const current = parseDate(text, allowed)
      setCursor(current.kind === 'ok' ? toLocalDate(current) : clampToRange(new Date()))
      setView(startView(mode))
    }
    setOpen(next)
  }

  const cursorYear = cursor.getFullYear()
  const selected = parsed.kind === 'ok' ? toLocalDate(parsed) : undefined
  const selectedYear = parsed.kind === 'ok' ? parsed.year : undefined
  const selectedMonth = parsed.kind === 'ok' && parsed.precision !== 'year' ? parsed.month : undefined
  const max = lastYear()

  const chooseYear = (year: number) => {
    if (mode === 'year') {
      pick(String(year).padStart(4, '0'))
      return
    }
    setCursor(new Date(year, cursor.getMonth(), 1))
    setView(mode === 'month' ? 'months' : 'days')
  }
  const chooseMonth = (month: number) => {
    if (mode === 'month') {
      pick(`${String(cursorYear).padStart(4, '0')}-${String(month + 1).padStart(2, '0')}`)
      return
    }
    setCursor(new Date(cursorYear, month, 1))
    setView('days')
  }

  const page = yearPage(cursorYear)
  const [pageFirst, setPageFirst] = useState<number | null>(null)
  useEffect(() => { if (open) setPageFirst(null) }, [open, cursorYear, view])
  const years = pageFirst === null
    ? page.years
    : Array.from({ length: 12 }, (_, i) => pageFirst + i).filter((y) => y >= FIRST_YEAR && y <= max)
  const firstOfPage = years[0] ?? page.first

  const todayAt = (p: DatePrecision) => todayText(p)
  const today = () => pick(todayAt(allowed.includes(mode) ? mode : coarsest(allowed)))

  return (
    <div className={cn('space-y-1', className)}>
      {label && (
        <Label htmlFor={id} className="text-xs">
          {label}
          {required && <span className="text-destructive" aria-hidden> *</span>}
        </Label>
      )}
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={onOpenChange}>
          <PopoverAnchor asChild>
            <div className="relative min-w-0 flex-1">
              <Input
                id={id}
                value={text}
                disabled={disabled}
                inputMode="numeric"
                autoComplete="off"
                placeholder={formatHint(precision ? [precision] : allowed)}
                aria-invalid={message ? true : undefined}
                aria-describedby={message ? `${id}-error` : undefined}
                className="pr-10"
                onChange={(event) => onType(event.target.value)}
                onBlur={() => setTouched(true)}
              />
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={disabled}
                  aria-label="Open the calendar"
                  className="absolute right-0.5 top-0.5 h-8 w-8 text-muted-foreground"
                >
                  <CalendarIcon className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
            </div>
          </PopoverAnchor>
          <PopoverContent align="start" collisionPadding={8} className="w-auto p-0">
            {view === 'days' && (
              <Calendar
                mode="single"
                captionLayout="dropdown"
                startMonth={new Date(FIRST_YEAR, 0)}
                endMonth={new Date(max, 11)}
                month={cursor}
                onMonthChange={setCursor}
                selected={selected}
                onSelect={(day) => { if (day) pick(todayTextOf(day)) }}
              />
            )}
            {view === 'months' && (
              <div className="w-[15.5rem] space-y-2 p-3">
                <div className="flex items-center justify-between">
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Previous year"
                    disabled={cursorYear <= FIRST_YEAR}
                    onClick={() => setCursor(new Date(cursorYear - 1, cursor.getMonth(), 1))}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button type="button" variant="ghost" size="sm" className="h-8 font-medium"
                    onClick={() => setView('years')}>
                    {cursorYear}
                  </Button>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Next year"
                    disabled={cursorYear >= max}
                    onClick={() => setCursor(new Date(cursorYear + 1, cursor.getMonth(), 1))}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-4 gap-1">
                  {MONTHS.map((name, index) => (
                    <Button key={name} type="button" size="sm"
                      variant={selectedYear === cursorYear && selectedMonth === index + 1 ? 'default' : 'ghost'}
                      className="h-8 px-0 text-xs" onClick={() => chooseMonth(index)}>
                      {name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            {view === 'years' && (
              <div className="w-[15.5rem] space-y-2 p-3">
                <div className="flex items-center justify-between">
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Earlier years"
                    disabled={firstOfPage <= FIRST_YEAR}
                    onClick={() => setPageFirst(Math.max(FIRST_YEAR, firstOfPage - 12))}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm font-medium tabular-nums">
                    {years[0]} - {years[years.length - 1]}
                  </span>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Later years"
                    disabled={(years[years.length - 1] ?? max) >= max}
                    onClick={() => setPageFirst(firstOfPage + 12)}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-4 gap-1">
                  {years.map((year) => (
                    <Button key={year} type="button" size="sm"
                      variant={selectedYear === year ? 'default' : 'ghost'}
                      className="h-8 px-0 text-xs tabular-nums" onClick={() => chooseYear(year)}>
                      {year}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            <div className="flex items-center justify-between gap-1 border-t border-border p-2">
              <div className="flex gap-1">
                {view !== 'years' && (
                  <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setView('years')}>
                    Years
                  </Button>
                )}
                {view === 'years' && mode === 'day' && (
                  <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setView('days')}>
                    Days
                  </Button>
                )}
                <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={today}>
                  Today
                </Button>
              </div>
              <Button type="button" variant="ghost" size="sm" className="h-8 text-xs"
                disabled={!text} onClick={() => { setText(''); setTouched(true); emit(''); setOpen(false) }}>
                Clear
              </Button>
            </div>
          </PopoverContent>
        </Popover>
        {hasChoice && (
          <select
            aria-label="Precision"
            value={mode}
            disabled={disabled}
            onChange={(event) => changePrecision(event.target.value as DatePrecision)}
            className={cn(
              'border-input dark:bg-input/30 h-9 w-24 shrink-0 rounded-md border bg-transparent px-2 text-base shadow-xs outline-none md:text-sm',
              'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:opacity-50',
            )}
          >
            {allowed.map((p) => <option key={p} value={p}>{PRECISION_NAMES[p]}</option>)}
          </select>
        )}
      </div>
      {message && (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">{message}</p>
      )}
    </div>
  )
}

function clampToRange(date: Date): Date {
  const year = Math.min(lastYear(), Math.max(FIRST_YEAR, date.getFullYear()))
  return year === date.getFullYear() ? date : new Date(year, date.getMonth(), 1)
}

function todayTextOf(day: Date): string {
  const month = String(day.getMonth() + 1).padStart(2, '0')
  const date = String(day.getDate()).padStart(2, '0')
  return `${String(day.getFullYear()).padStart(4, '0')}-${month}-${date}`
}
