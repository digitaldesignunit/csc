'use client'

import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

export type DatasetRole = 'contributor' | 'reviewer' | 'moderator'

export const DATASET_ROLES: { value: DatasetRole; label: string; hint: string }[] = [
  { value: 'contributor', label: 'Contributor', hint: 'adds components, states and evidence' },
  { value: 'reviewer', label: 'Reviewer', hint: 'reviews evidence (four eyes)' },
  { value: 'moderator', label: 'Moderator', hint: 'publishes, withdraws, manages members' },
]

/** Dataset roles are a set, not a ladder (spec section 3.6). */
export default function RoleCheckboxes({
  idPrefix,
  value,
  onChange,
  disabled = false,
  compact = false,
}: {
  idPrefix: string
  value: DatasetRole[]
  onChange: (roles: DatasetRole[]) => void
  disabled?: boolean
  compact?: boolean
}) {
  const toggle = (role: DatasetRole, checked: boolean) => {
    const next = new Set(value)
    if (checked) next.add(role)
    else next.delete(role)
    onChange(DATASET_ROLES.map((r) => r.value).filter((r) => next.has(r)))
  }
  return (
    <div className={compact ? 'flex flex-wrap gap-3' : 'space-y-2'}>
      {DATASET_ROLES.map((role) => (
        <div key={role.value} className="flex items-start gap-2">
          <Checkbox
            id={`${idPrefix}-${role.value}`}
            checked={value.includes(role.value)}
            onCheckedChange={(checked) => toggle(role.value, checked === true)}
            disabled={disabled}
          />
          <Label htmlFor={`${idPrefix}-${role.value}`} className="text-sm font-normal leading-tight">
            {role.label}
            {!compact && <span className="block text-xs text-muted-foreground">{role.hint}</span>}
          </Label>
        </div>
      ))}
    </div>
  )
}
