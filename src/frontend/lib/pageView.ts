'use client'

/**
 * The small store between the component page and the session monitor (issue
 * 35): the page reports whether an anonymous visitor would see all of it. The
 * monitor lives in the root layout, the page below it, so a store outside the
 * React tree is the shortest link.
 */
import { useEffect, useLayoutEffect, useSyncExternalStore } from 'react'

import type { PageView } from '@/lib/sessionExpiry'

let current: PageView = null
const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

function set(next: PageView): void {
  if (next === current) return
  if (next && current && next.publicToAnonymous === current.publicToAnonymous) return
  current = next
  listeners.forEach((listener) => listener())
}

/** The monitor reads what the page on screen reports. */
export function usePageView(): PageView {
  return useSyncExternalStore(subscribe, () => current, () => null)
}

// a layout effect runs before the passive effects of the monitor, so a page
// that mounts reports before the monitor decides on it
const useBeforeEffects = typeof window === 'undefined' ? useEffect : useLayoutEffect

/** The component page reports its view; it reports nothing once it is gone. */
export function useReportPageView(publicToAnonymous: boolean): void {
  useBeforeEffects(() => {
    set({ publicToAnonymous })
    return () => set(null)
  }, [publicToAnonymous])
}
