// app/components/[component_id]/page.tsx
import ComponentDetailCard from '@/components/components/ComponentDetailCard'
import ComponentViewer from '@/components/components/ComponentViewer'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { Package } from 'lucide-react'
import { headers } from 'next/headers'
import { redirect, notFound } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type PageParams = { component_id: string }

export default async function ComponentDetailPage({
  params,
}: {
  params: Promise<PageParams>
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const { component_id } = await params

  const res = await fetch(
    `${base}/api/backend/identities/${encodeURIComponent(component_id)}/compose`,
    {
      cache: 'no-store',
      headers: { cookie },
    },
  )

  if (res.status === 401) {
    redirect(`/auth/signin?callbackUrl=/components/${component_id}`)
  }
  if (res.status === 404) {
    notFound()
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to fetch compose ${component_id}: ${res.status} ${body}`,
    )
  }

  const catalog = (await res.json()) as CatalogComponent

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Package className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Component Details</h1>
        </div>
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        <ComponentViewer catalog={catalog} />
        <ComponentDetailCard variant="compose" catalog={catalog} />
      </div>
    </div>
  )
}
