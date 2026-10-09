'use client'

/**
 * What a queue card needs beyond its list row (size, shape class, what a
 * correction changes, the result of a record), read once per row and kept
 * while the row stays in the list. A failed read leaves the card with its row
 * facts; it never blocks the decision.
 */
import { useEffect, useRef, useState } from 'react'

export function useDetails<R, V>(
  rows: R[],
  keyOf: (row: R) => string,
  load: (row: R) => Promise<V>,
): Record<string, V | null | undefined> {
  const [details, setDetails] = useState<Record<string, V | null>>({})
  const asked = useRef<Set<string>>(new Set())
  const loadRef = useRef(load)
  loadRef.current = load
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    for (const row of rows) {
      const key = keyOf(row)
      if (asked.current.has(key)) continue
      asked.current.add(key)
      loadRef.current(row)
        .catch(() => null)
        .then((value) => { if (mounted.current) setDetails((now) => ({ ...now, [key]: value })) })
    }
    // keyOf is a plain accessor of the caller
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows])

  return details
}
