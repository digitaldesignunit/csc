'use client'

/**
 * Small form controls of the evidence form: a field shell with label, "?"
 * help and errors, a native select (the best picker on a phone), and the
 * list of numbers (readings) with tap-to-reject chips.
 */
import { useState } from 'react'
import { Plus, X } from 'lucide-react'

import Help from '@/components/ui/help'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { parseNumber } from '@/lib/evidence/schema'
import { cn } from '@/lib/utils'

export function Field({
  id,
  label,
  help,
  required,
  errors,
  children,
  className,
}: {
  id: string
  label: string
  help?: string
  required?: boolean
  errors?: string[]
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1', className)}>
      <div className="flex items-center gap-1">
        <Label htmlFor={id} className="text-xs">
          {label}
          {required && <span className="text-destructive" aria-hidden> *</span>}
        </Label>
        {help ? <Help text={help} label={label} /> : null}
      </div>
      {children}
      {errors && errors.length > 0 && (
        <ul className="space-y-0.5" role="alert">
          {errors.map((message) => (
            <li key={message} className="text-xs text-destructive">{message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function NativeSelect({
  id,
  value,
  onChange,
  options,
  placeholder,
  disabled,
  className,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
  disabled?: boolean
  className?: string
}) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className={cn(
        'border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-2 text-base shadow-xs outline-none md:text-sm',
        'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:opacity-50',
        className,
      )}
    >
      <option value="">{placeholder ?? 'Select...'}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  )
}

/**
 * Numbers typed one by one (readings): Enter or the plus adds, a tap on a
 * chip toggles "rejected" where the list can flag rejections (they stay in
 * the list, flagged, never deleted: the discard rule needs them) and the
 * cross removes an entry. Several values in one go (pasted, separated by
 * space, comma or line break) are accepted.
 */
export function NumberList({
  id,
  values,
  onChange,
  rejected,
  onRejectedChange,
  min,
  unit,
}: {
  id: string
  values: string[]
  onChange: (values: string[]) => void
  rejected?: number[]
  onRejectedChange?: (indices: number[]) => void
  min?: number
  unit?: string
}) {
  const [draft, setDraft] = useState('')
  const [note, setNote] = useState<string | null>(null)

  const commit = () => {
    const parts = draft.split(/[\s;]+/).map((p) => p.trim()).filter(Boolean)
    if (parts.length === 0) return
    const bad = parts.filter((p) => parseNumber(p) === null)
    if (bad.length) {
      setNote(`Not a number: ${bad.slice(0, 3).join(', ')}`)
      return
    }
    setNote(null)
    onChange([...values, ...parts.map((p) => String(parseNumber(p)))])
    setDraft('')
  }

  const remove = (index: number) => {
    onChange(values.filter((_, i) => i !== index))
    if (rejected && onRejectedChange) {
      onRejectedChange(
        rejected.filter((i) => i !== index).map((i) => (i > index ? i - 1 : i)),
      )
    }
  }

  const toggleRejected = (index: number) => {
    if (!rejected || !onRejectedChange) return
    onRejectedChange(
      rejected.includes(index)
        ? rejected.filter((i) => i !== index)
        : [...rejected, index].sort((a, b) => a - b),
    )
  }

  const rejectedCount = rejected?.length ?? 0
  const valid = values.length - rejectedCount

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          inputMode="decimal"
          enterKeyHint="done"
          placeholder={unit ? `Reading (${unit})` : 'Value'}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              commit()
            }
          }}
        />
        <Button type="button" variant="outline" size="icon" onClick={commit} aria-label="Add value">
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {note && <p className="text-xs text-destructive" role="alert">{note}</p>}
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Entered values">
          {values.map((value, index) => {
            const flagged = rejected?.includes(index) ?? false
            return (
              <li
                key={`${index}-${value}`}
                className={cn(
                  'inline-flex items-center overflow-hidden rounded-md border text-sm',
                  flagged ? 'border-red-400 bg-red-50 text-red-900 line-through dark:bg-red-950/40 dark:text-red-100' : 'border-border bg-muted/40',
                )}
              >
                <button
                  type="button"
                  className="px-2 py-1 tabular-nums"
                  onClick={() => toggleRejected(index)}
                  disabled={!onRejectedChange}
                  aria-pressed={onRejectedChange ? flagged : undefined}
                  title={onRejectedChange ? (flagged ? 'Rejected: tap to count it again' : 'Tap to reject this reading') : undefined}
                >
                  {value}
                </button>
                <button
                  type="button"
                  className="border-l border-border/60 px-1.5 py-1 text-muted-foreground hover:text-destructive"
                  onClick={() => remove(index)}
                  aria-label={`Remove ${value}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        {values.length} entered
        {onRejectedChange ? `, ${rejectedCount} rejected, ${valid} valid` : ''}
        {min ? ` (at least ${min} valid are needed)` : ''}
        {onRejectedChange && values.length > 0 ? '. Tap a value to reject it.' : ''}
      </p>
    </div>
  )
}
