'use client'

/**
 * The evidence records of the component on screen, loaded once for the cards
 * that need them (Properties for the outranked records, the record list) and
 * reloaded after a change. A change also bumps `reloadKey`, which the History
 * card watches to reload its timeline.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import type { EvidenceView } from '@/generated'
import { BackendError } from '@/lib/backend'
import { loadEvidenceOf } from '@/lib/evidence/api'
import { useMe } from '@/lib/me'

type EvidenceData = {
  records: EvidenceView[] | null
  error: string | null
  /** call after a record changed: reloads the records and the history */
  changed: () => void
  reloadKey: number
}

const Context = createContext<EvidenceData | null>(null)

export function EvidenceDataProvider({ identityId, children }: { identityId: string; children: ReactNode }) {
  const { me } = useMe()
  const [records, setRecords] = useState<EvidenceView[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(() => {
    loadEvidenceOf(identityId)
      .then((rows) => { setRecords(rows); setError(null) })
      .catch((err) => {
        setRecords([])
        setError(err instanceof BackendError ? err.message : 'Could not load the evidence.')
      })
  }, [identityId])

  useEffect(() => { load() }, [load, me?._id])

  const value = useMemo<EvidenceData>(() => ({
    records,
    error,
    reloadKey,
    changed: () => { load(); setReloadKey((k) => k + 1) },
  }), [records, error, reloadKey, load])

  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useEvidenceData(): EvidenceData {
  const value = useContext(Context)
  if (!value) throw new Error('useEvidenceData needs an EvidenceDataProvider')
  return value
}
