'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { CATALOG_META_CUSTOM } from '@/lib/catalogCreate'

const UNSET = '__unset__'

type Props = {
  id: string
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
  customPlaceholder?: string
  required?: boolean
}

function valueIsCustom(value: string, options: string[]): boolean {
  const trimmed = value.trim()
  return trimmed !== '' && !options.includes(trimmed)
}

export default function CatalogMetaSelect({
  id,
  label,
  value,
  options,
  onChange,
  customPlaceholder = 'Enter custom value',
  required,
}: Props) {
  const customInputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const [customMode, setCustomMode] = useState(() => valueIsCustom(value, options))

  useEffect(() => {
    if (valueIsCustom(value, options)) {
      setCustomMode(true)
    }
  }, [value, options])

  const selectValue = customMode
    ? CATALOG_META_CUSTOM
    : value.trim() === ''
      ? UNSET
      : value

  const showCustom = customMode

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={selectValue === UNSET ? undefined : selectValue}
        onValueChange={next => {
          if (next === CATALOG_META_CUSTOM) {
            setCustomMode(true)
            if (options.includes(value)) {
              onChange('')
            }
            window.setTimeout(() => customInputRef.current?.focus(), 0)
            return
          }
          if (next === UNSET) return
          setCustomMode(false)
          onChange(next)
        }}
        required={required && !customMode}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent position="item-aligned" className="max-h-72">
          {options.map(opt => (
            <SelectItem key={opt} value={opt}>
              {opt}
            </SelectItem>
          ))}
          <SelectItem value={CATALOG_META_CUSTOM}>Other (custom)...</SelectItem>
        </SelectContent>
      </Select>
      {showCustom && (
        <Input
          ref={customInputRef}
          id={`${id}-custom`}
          list={options.length > 0 ? listId : undefined}
          aria-label={`Custom ${label.toLowerCase()}`}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={customPlaceholder}
          required={required}
          className="w-full"
          autoComplete="off"
          enterKeyHint="done"
        />
      )}
      {options.length > 0 && (
        <datalist id={listId}>
          {options.map(opt => (
            <option key={opt} value={opt} />
          ))}
        </datalist>
      )}
    </div>
  )
}
