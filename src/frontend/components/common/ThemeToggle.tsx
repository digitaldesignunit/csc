'use client'

import { useTheme } from 'next-themes'
import { Button } from '@/components/ui/button'
import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

export default function ThemeToggle() {
  const { theme, setTheme, systemTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => { setMounted(true) }, [])

  const current = theme === 'system' ? systemTheme : theme
  const isDark = current === 'dark'

  if (!mounted) {
    return (
      <Button variant='outline' size='icon' className='h-9 w-9' aria-label='Toggle theme'>
        <Sun className='h-4 w-4' />
      </Button>
    )
  }

  return (
    <Button
      variant='outline'
      size='icon'
      className='h-9 w-9 hover:bg-accent dark:hover:bg-accent transition-colors'
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label='Toggle theme'
      title={isDark ? 'Switch to light' : 'Switch to dark'}
    >
      {/* fancy crossfade between icons */}
      <Sun className='h-4 w-4 transition-opacity duration-200 opacity-100 dark:opacity-0' />
      <Moon className='h-4 w-4 absolute transition-opacity duration-200 opacity-0 dark:opacity-100' />
    </Button>
  )
}
