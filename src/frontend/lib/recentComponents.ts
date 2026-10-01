'use client'

/**
 * "Recent" in the sidebar (decision 8.29): the last component pages opened,
 * kept in this browser only. Storage may be unavailable (private windows,
 * blocked site data); every access is guarded and the list then stays empty.
 */
import { useCallback, useEffect, useState } from 'react'

export type RecentComponent = { id: string; label: string }

const KEY = 'csc-recent-components'
const EVENT = 'csc-recent-components-changed'
export const RECENT_LIMIT = 5

function read(): RecentComponent[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(parsed)
      ? parsed.filter((r) => typeof r?.id === 'string' && typeof r?.label === 'string')
      : []
  } catch {
    return []
  }
}

function write(items: RecentComponent[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items.slice(0, RECENT_LIMIT)))
  } catch {
    // storage blocked: the list simply is not remembered
  }
  window.dispatchEvent(new Event(EVENT))
}

export function recordRecentComponent(item: RecentComponent): void {
  write([item, ...read().filter((r) => r.id !== item.id)])
}

export function useRecentComponents() {
  const [items, setItems] = useState<RecentComponent[]>([])

  useEffect(() => {
    const refresh = () => setItems(read())
    refresh()
    window.addEventListener(EVENT, refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener(EVENT, refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  const remove = useCallback((id: string) => {
    write(read().filter((r) => r.id !== id))
  }, [])
  const clear = useCallback(() => write([]), [])

  return { items, remove, clear }
}
