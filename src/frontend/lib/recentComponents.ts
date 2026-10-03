'use client'

/**
 * "Recent" in the sidebar (decision 8.29): the last component pages opened,
 * kept in this browser, per signed-in user (decision 8.86). Nothing is
 * recorded for anonymous visitors, the list is cleared when the user signs
 * out or the session expires, and the key before 8.86 (one list for the whole
 * browser) is removed on first load. Storage may be unavailable (private
 * windows, blocked site data); every access is guarded and the list then
 * stays empty.
 */
import { useCallback, useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'

export type RecentComponent = { id: string; label: string }

const PREFIX = 'csc-recent-components'
const LEGACY_KEY = PREFIX
const EVENT = 'csc-recent-components-changed'
export const RECENT_LIMIT = 5

const keyOf = (userId: string) => `${PREFIX}:${userId}`

function read(userId: string): RecentComponent[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(keyOf(userId)) ?? '[]')
    return Array.isArray(parsed)
      ? parsed.filter((r) => typeof r?.id === 'string' && typeof r?.label === 'string')
      : []
  } catch {
    return []
  }
}

function write(userId: string, items: RecentComponent[]): void {
  try {
    window.localStorage.setItem(keyOf(userId), JSON.stringify(items.slice(0, RECENT_LIMIT)))
  } catch {
    // storage blocked: the list simply is not remembered
  }
  window.dispatchEvent(new Event(EVENT))
}

/**
 * The signed-in user's id, or null: not while the session is loading, not
 * for an anonymous visitor and not for a session that carries an error.
 */
export function useRecentUserId(): string | null {
  const { data: session, status } = useSession()
  const error = (session as { error?: string } | null)?.error
  if (status !== 'authenticated' || error) return null
  return session?.user?.id ?? null
}

/** Removes the user's list (all users' lists when the id is unknown). */
export function forgetRecentComponents(userId?: string | null): void {
  try {
    if (userId) {
      window.localStorage.removeItem(keyOf(userId))
    } else {
      for (let i = window.localStorage.length - 1; i >= 0; i -= 1) {
        const key = window.localStorage.key(i)
        if (key && key.startsWith(`${PREFIX}:`)) window.localStorage.removeItem(key)
      }
    }
  } catch {
    // storage blocked: nothing was kept
  }
  window.dispatchEvent(new Event(EVENT))
}

function removeLegacyKey(): void {
  try {
    window.localStorage.removeItem(LEGACY_KEY)
  } catch {
    // storage blocked: nothing was kept
  }
}

export function recordRecentComponent(userId: string, item: RecentComponent): void {
  write(userId, [item, ...read(userId).filter((r) => r.id !== item.id)])
}

export function useRecentComponents(userId: string | null) {
  const [items, setItems] = useState<RecentComponent[]>([])

  useEffect(() => {
    removeLegacyKey()
  }, [])

  useEffect(() => {
    const refresh = () => setItems(userId ? read(userId) : [])
    refresh()
    window.addEventListener(EVENT, refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener(EVENT, refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [userId])

  const remove = useCallback((id: string) => {
    if (userId) write(userId, read(userId).filter((r) => r.id !== id))
  }, [userId])
  const clear = useCallback(() => {
    if (userId) write(userId, [])
  }, [userId])

  return { items: userId ? items : [], remove, clear }
}
