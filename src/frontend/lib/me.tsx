'use client'

/**
 * The signed-in caller with their roles per dataset (`GET /users/me`, plan
 * P3). The backend enforces every rule; the frontend only uses this to show
 * or hide controls. Nothing role-related besides the global role is in the
 * session token, so this is fetched per session.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'

import type { Me } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'

type DatasetRole = 'contributor' | 'reviewer' | 'moderator'

type MeContextValue = {
  me: Me | null
  loading: boolean
  refresh: () => Promise<void>
  isAdmin: boolean
  /** Moderates at least one dataset (or is admin). */
  moderatesAny: boolean
  moderates: (dataset: string | null | undefined) => boolean
  /** Roles in a dataset; admin holds every role implicitly. */
  rolesIn: (dataset: string | null | undefined) => DatasetRole[]
}

const ALL_ROLES: DatasetRole[] = ['contributor', 'reviewer', 'moderator']

const MeContext = createContext<MeContextValue | null>(null)

export function MeProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()
  const signedIn = status === 'authenticated' && !(session as { error?: string } | null)?.error
  const userKey = signedIn ? String((session?.user as { email?: string } | undefined)?.email ?? '') : ''
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!signedIn) {
      setMe(null)
      return
    }
    setLoading(true)
    try {
      setMe(await backendJson<Me>('/users/me'))
    } catch {
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [signedIn])

  useEffect(() => {
    void refresh()
  }, [refresh, userKey])

  const value = useMemo<MeContextValue>(() => {
    const isAdmin = me?.role === 'admin'
    const moderated = new Set(me?.moderated_datasets ?? [])
    return {
      me,
      loading,
      refresh,
      isAdmin,
      moderatesAny: isAdmin || moderated.size > 0,
      moderates: (dataset) => isAdmin || (!!dataset && moderated.has(dataset)),
      rolesIn: (dataset) => {
        if (isAdmin) return ALL_ROLES
        const row = (me?.memberships ?? []).find((m) => m.dataset === dataset)
        return (row?.roles ?? []) as DatasetRole[]
      },
    }
  }, [me, loading, refresh])

  return <MeContext.Provider value={value}>{children}</MeContext.Provider>
}

export function useMe(): MeContextValue {
  const context = useContext(MeContext)
  if (!context) throw new Error('useMe must be used within MeProvider')
  return context
}
