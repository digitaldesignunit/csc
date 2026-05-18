'use client'

import { useCallback, useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter, useParams } from 'next/navigation'
import { Archive } from 'lucide-react'
import type { CatalogComponent } from '@/generated/CatalogModels'
import ComponentViewer from '@/components/components/ComponentViewer'
import ComponentDetailCard from '@/components/components/ComponentDetailCard'

export default function ArchivedComponentDetailPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const component_id = params.component_id as string

  const [catalog, setCatalog] = useState<CatalogComponent | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Redirect non-admin users
  useEffect(() => {
    if (status === 'loading') return

    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [session, status, router])

  const fetchArchivedComponent = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(component_id)}/compose`,
        { credentials: 'include' },
      )

      if (response.status === 404) {
        setError('Archived component not found')
        setCatalog(null)
        return
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`)
      }

      const json = (await response.json()) as CatalogComponent
      setCatalog(json)
    } catch (err) {
      console.error('Failed to fetch archived component:', err)
      setError('Failed to load archived component')
      setCatalog(null)
    } finally {
      setLoading(false)
    }
  }, [component_id])

  // Fetch archived component
  useEffect(() => {
    if (session?.user?.role === 'admin' && !session.error && component_id) {
      fetchArchivedComponent()
    }
  }, [session, component_id, fetchArchivedComponent])

  // Loading state
  if (status === 'loading' || loading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </div>
    )
  }

  // Not admin
  if (!session?.user || session.user.role !== 'admin') {
    return null
  }

  // Error state
  if (error) {
    return (
      <div className="container mx-auto p-6 space-y-6 max-w-full">
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <Archive className="h-8 w-8 text-primary" />
            <h1 className="text-2xl sm:text-3xl font-bold">Archived Component</h1>
          </div>
        </div>

        <div className="text-center py-12">
          <p className="text-muted-foreground">{error}</p>
        </div>
      </div>
    )
  }

  if (!catalog) {
    return null
  }

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Archive className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Archived Component</h1>
        </div>
        <p className="text-muted-foreground">
          This component is archived and not visible in the main Catalog.
        </p>
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        <ComponentViewer catalog={catalog} />
        <ComponentDetailCard variant="compose" catalog={catalog} isArchived />
      </div>
    </div>
  )
}
