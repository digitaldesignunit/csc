// app/components/[component_id]/page.tsx
import { Suspense } from 'react'
import ComponentDetailCard from '@/components/components/ComponentDetailCard'
import ComponentViewer from '@/components/components/ComponentViewer'
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

  // Fetch the full component doc via the proxy
  const res = await fetch(
    `${base}/api/backend/components/${encodeURIComponent(component_id)}`,
    {
      cache: 'no-store',
      headers: { cookie }, // forward session so middleware/proxy allow the call
    }
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
      `Failed to fetch component ${component_id}: ${res.status} ${body}`
    )
  }

  const component_data = await res.json()

  return (
    <div className="grid gap-2 m-2">
      <ComponentViewer component_data={component_data} />
      <ComponentDetailCard component_data={component_data} />
    </div>
  )
}
