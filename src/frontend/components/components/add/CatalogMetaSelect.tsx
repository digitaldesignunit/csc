'use client'

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

export default function CatalogMetaSelect({
  id,
  label,
  value,
  options,
  onChange,
  customPlaceholder = 'Enter custom value',
  required,
}: Props) {
  const selectValue =
    value.trim() === ''
      ? UNSET
      : options.includes(value)
        ? value
        : CATALOG_META_CUSTOM

  const showCustom = selectValue === CATALOG_META_CUSTOM

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={selectValue}
        onValueChange={next => {
          if (next === CATALOG_META_CUSTOM) {
            onChange('')
            return
          }
          onChange(next)
        }}
        required={required}
      >
        <SelectTrigger id={id}>
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={UNSET} disabled>
            Select {label.toLowerCase()}
          </SelectItem>
          {options.map(opt => (
            <SelectItem key={opt} value={opt}>
              {opt}
            </SelectItem>
          ))}
          <SelectItem value={CATALOG_META_CUSTOM}>Other (custom)…</SelectItem>
        </SelectContent>
      </Select>
      {showCustom && (
        <Input
          aria-label={`Custom ${label.toLowerCase()}`}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={customPlaceholder}
          required={required}
        />
      )}
    </div>
  )
}
