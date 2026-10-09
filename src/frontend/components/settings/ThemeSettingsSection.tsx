'use client'

import { Palette } from 'lucide-react'
import { useTheme } from 'next-themes'
import { useEffect, useState } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const OPTIONS = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
] as const

/** Settings, "Appearance": three radio buttons, nothing to explain (decision 8.118 S6). */
export default function ThemeSettingsSection() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Palette className="h-4 w-4 text-primary" aria-hidden />
          Appearance
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div role="radiogroup" aria-label="Appearance" className="flex flex-wrap gap-4 text-sm">
          {OPTIONS.map((option) => (
            <label key={option.value} className="flex cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="appearance"
                value={option.value}
                className="h-4 w-4 accent-primary"
                checked={mounted && (theme ?? 'system') === option.value}
                onChange={() => setTheme(option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
