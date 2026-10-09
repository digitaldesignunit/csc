'use client'

/**
 * The registry the form and the cards read (`GET /evidence/methods`,
 * `/evidence/quantities`, the envelope help texts): loaded once per page
 * load and shared by every component that asks.
 */
import { useEffect, useState } from 'react'

import {
  loadEnvelopeHelp,
  loadMethods,
  loadQuantities,
  type EnvelopeHelp,
  type MethodInfo,
  type QuantityInfo,
} from '@/lib/evidence/api'

export type Registry = {
  methods: MethodInfo[]
  quantities: QuantityInfo[]
  help: EnvelopeHelp
}

export function useRegistry(): { registry: Registry | null; error: string | null } {
  const [registry, setRegistry] = useState<Registry | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    Promise.all([loadMethods(), loadQuantities(), loadEnvelopeHelp()])
      .then(([methods, quantities, help]) => {
        if (!cancelled) setRegistry({ methods, quantities, help })
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load the evidence methods')
      })
    return () => { cancelled = true }
  }, [])
  return { registry, error }
}
