'use client'

import { use, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { Pencil } from 'lucide-react'

import ComponentEditForm from '@/components/components/ComponentEditForm'
import { composeCatalogToExtendedRow } from '@/components/components/ComponentDetailCard'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { ExtendedComponentModel } from '@/generated/ComponentModel'

type PageParams = { component_id: string }

function isConsumedIdentity(consumedAt: unknown): boolean {
  return consumedAt !== undefined && consumedAt !== null && String(consumedAt).trim() !== ''
}

export default function ComponentEditPage({
  params,
}: {
  params: Promise<PageParams>
}) {
  const { component_id } = use(params)
  const router = useRouter()
  const { data: session, status } = useSession()

  const [component, setComponent] = useState<ExtendedComponentModel | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFoundState, setNotFoundState] = useState(false)

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user || session.error === 'ApiTokenExpired') {
      router.push(`/auth/signin?callbackUrl=/components/${component_id}/edit`)
      return
    }
    if (session.user.role !== 'admin') {
      router.push(`/components/${component_id}`)
    }
  }, [session, status, router, component_id])

  useEffect(() => {
    if (session?.user?.role !== 'admin') return
    let cancelled = false

    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await fetch(
          `/api/backend/identities/${encodeURIComponent(component_id)}/compose`,
          { cache: 'no-store', credentials: 'include' },
        )
        if (cancelled) return
        if (res.status === 404) {
          setNotFoundState(true)
          return
        }
        if (!res.ok) {
          throw new Error(`Failed to load identity (${res.status})`)
        }
        const catalog = (await res.json()) as CatalogComponent
        if (isConsumedIdentity(catalog.identity.consumed_at)) {
          router.replace(`/components/${component_id}`)
          return
        }
        if (!cancelled) {
          setComponent(composeCatalogToExtendedRow(catalog))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unknown error')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [session, component_id, router])

  if (status === 'loading' || (session?.user?.role === 'admin' && loading)) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
        </div>
      </div>
    )
  }

  if (!session?.user || session.user.role !== 'admin') {
    return null
  }

  if (notFoundState) {
    return (
      <div className="container mx-auto max-w-3xl space-y-6 p-6">
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Identity not found.
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto max-w-3xl space-y-6 p-6">
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load identity: {error}
        </div>
      </div>
    )
  }

  if (!component) return null

  return (
    <div className="container mx-auto max-w-3xl space-y-6 p-6">
      <div className="mb-4 sm:mb-6">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Pencil className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Edit Component</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Update the human-readable name, classification, color, and
          location. Structural fields (geometry, bounding box, frames) and
          lifecycle state (validation, reservation) are managed separately.
          Complexity is derived from geometry and cannot be edited here.
        </p>
        <div className="mt-3 break-all rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">
          <span className="text-muted-foreground">Identity ID:</span>{' '}
          {component._id}
        </div>
      </div>

      <ComponentEditForm component_data={component} />
    </div>
  )
}
