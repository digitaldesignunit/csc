'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import { Wrench } from 'lucide-react'

import { READ_ONLY_BANNER, READ_ONLY_POLL_MS, VERSION_PATH, parseReadOnly } from '@/lib/readOnly'

export const ReadOnlyContext = createContext(false)

/**
 * One poll of `/version` for the whole app (decision 8.154): on load, then once
 * a minute while the tab is visible, and again when the tab becomes visible.
 * A failed request leaves the state as it was.
 */
export function ReadOnlyProvider({ children }: { children: React.ReactNode }) {
  const [readOnly, setReadOnly] = useState(false)

  useEffect(() => {
    let alive = true
    async function check() {
      if (document.visibilityState === 'hidden') return
      try {
        const response = await fetch(VERSION_PATH, { cache: 'no-store' })
        if (!response.ok) return
        const next = parseReadOnly(await response.json())
        if (alive) setReadOnly(next)
      } catch {
        // offline or the backend restarting: keep what we knew
      }
    }
    void check()
    const timer = window.setInterval(() => void check(), READ_ONLY_POLL_MS)
    document.addEventListener('visibilitychange', check)
    return () => {
      alive = false
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
    }
  }, [])

  return <ReadOnlyContext.Provider value={readOnly}>{children}</ReadOnlyContext.Provider>
}

/** `true` while the backend is read-only. */
export function useReadOnly(): boolean {
  return useContext(ReadOnlyContext)
}

/** The banner on every page while the backend is read-only. */
export function ReadOnlyBanner() {
  const readOnly = useReadOnly()
  if (!readOnly) return null
  return (
    <div
      role="status"
      className="flex items-start gap-2 border-b border-amber-300 bg-amber-100 px-4 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
    >
      <Wrench className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{READ_ONLY_BANNER}</span>
    </div>
  )
}
