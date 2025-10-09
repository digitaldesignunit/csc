'use client'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { useEffect, useState } from 'react'

export default function ThemeSettingsSection() {
  const { theme, setTheme, systemTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Sun className="h-5 w-5 text-primary" />
            <div>
              <CardTitle>Theme Settings</CardTitle>
              <CardDescription>Choose your preferred theme appearance</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
          </div>
        </CardContent>
      </Card>
    )
  }

  const currentTheme = theme === 'system' ? systemTheme : theme
  const isDark = currentTheme === 'dark'

  const themeOptions = [
    {
      value: 'light',
      label: 'Light',
      description: 'Always use light theme',
      icon: Sun,
      isActive: theme === 'light'
    },
    {
      value: 'dark',
      label: 'Dark',
      description: 'Always use dark theme',
      icon: Moon,
      isActive: theme === 'dark'
    },
    {
      value: 'system',
      label: 'System',
      description: 'Follow your system preference',
      icon: Monitor,
      isActive: theme === 'system'
    }
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Sun className="h-5 w-5 text-primary" />
          <div>
            <CardTitle>Theme Settings</CardTitle>
            <CardDescription>Choose your preferred theme appearance</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Current Theme Display */}
        <div className="p-4 bg-muted/30 border rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium mb-1">Current Theme</h4>
              <p className="text-sm text-muted-foreground">
                {theme === 'system' 
                  ? `System (${systemTheme})` 
                  : theme === 'light' 
                    ? 'Light' 
                    : 'Dark'
                }
              </p>
            </div>
            <div className="flex items-center gap-2">
              {isDark ? (
                <Moon className="h-5 w-5 text-primary" />
              ) : (
                <Sun className="h-5 w-5 text-primary" />
              )}
            </div>
          </div>
        </div>

        {/* Theme Options */}
        <div className="space-y-3">
          <Label className="text-base font-medium">Choose Theme</Label>
          <div className="grid gap-3">
            {themeOptions.map((option) => {
              const Icon = option.icon
              return (
                <Button
                  key={option.value}
                  variant={option.isActive ? "default" : "outline"}
                  className={`h-auto p-4 justify-start text-left ${
                    option.isActive 
                      ? "bg-primary text-primary-foreground" 
                      : "hover:bg-accent"
                  }`}
                  onClick={() => setTheme(option.value)}
                >
                  <div className="flex items-center gap-3 w-full">
                    <Icon className="h-5 w-5 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="font-medium">{option.label}</div>
                      <div className="text-sm opacity-80">{option.description}</div>
                    </div>
                    {option.isActive && (
                      <div className="w-2 h-2 rounded-full bg-current opacity-60" />
                    )}
                  </div>
                </Button>
              )
            })}
          </div>
        </div>

        {/* Theme Information */}
        <div className="text-xs text-muted-foreground space-y-1 pt-4 border-t">
          <p><strong>Storage:</strong> Your theme preference is saved in localStorage.</p>
          <p><strong>System Theme:</strong> Automatically follows your OS dark/light mode setting.</p>
          <p><strong>Persistence:</strong> Your choice will be remembered across browser sessions.</p>
        </div>
      </CardContent>
    </Card>
  )
}
