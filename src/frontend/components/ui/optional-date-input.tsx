'use client'

import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import { CalendarIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Label } from '@/components/ui/label'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { formatYyyyMmDd, parseYyyyMmDd } from '@/lib/dateInput'
import { cn } from '@/lib/utils'

type OptionalDateInputProps = {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  className?: string
}

/**
 * Optional date field using shadcn Popover + Calendar (DatePicker pattern).
 * Cancel closes without applying a new day; Clear empties the field.
 */
export function OptionalDateInput({
  id,
  label,
  value,
  onChange,
  className,
}: OptionalDateInputProps) {
  const [open, setOpen] = useState(false)
  const committed = parseYyyyMmDd(value)
  const [pending, setPending] = useState<Date | undefined>(committed)

  useEffect(() => {
    if (open) {
      setPending(parseYyyyMmDd(value))
    }
  }, [open, value])

  const handleOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      setPending(parseYyyyMmDd(value))
    }
  }

  const handleCancel = () => {
    setPending(parseYyyyMmDd(value))
    setOpen(false)
  }

  const handleClear = () => {
    onChange('')
    setPending(undefined)
    setOpen(false)
  }

  const handleSelect = (day: Date | undefined) => {
    setPending(day)
    if (day) {
      onChange(formatYyyyMmDd(day))
      setOpen(false)
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      <Label id={`${id}-label`} htmlFor={id}>
        {label}
      </Label>
      <div className="flex gap-2">
        <Popover open={open} onOpenChange={handleOpenChange}>
          <PopoverTrigger asChild>
            <Button
              id={id}
              type="button"
              variant="outline"
              aria-labelledby={`${id}-label`}
              className={cn(
                'min-w-0 flex-1 justify-start text-left font-normal',
                !committed && 'text-muted-foreground',
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4 shrink-0" />
              {committed ? format(committed, 'PPP') : <span>Pick a date</span>}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              selected={pending}
              onSelect={handleSelect}
              defaultMonth={pending ?? committed}
            />
            <div className="flex justify-end gap-2 border-t border-border p-2">
              <Button type="button" variant="ghost" size="sm" onClick={handleCancel}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleClear}
                disabled={!value && !pending}
              >
                Clear
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  )
}
