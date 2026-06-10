import { DesignModel } from '@/generated/DesignModel'
import { headers } from 'next/headers'
import { redirect, notFound } from 'next/navigation'
import DesignViewer from '@/components/designs/DesignViewer'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import DesignDetailCard from '@/components/designs/DesignDetailCard'
import DesignPlacementList from '@/components/designs/DesignPlacementList'
import { Layers } from 'lucide-react'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

async function fetchDesign(designId: string): Promise<DesignModel> {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const fetchOpts = { cache: 'no-store' as const, headers: { cookie } }

  const response = await fetch(
    `${base}/api/backend/designs/${designId}`,
    fetchOpts
  )

  if (response.status === 401) {
    redirect('/auth/signin?callbackUrl=/designs')
  }
  
  if (response.status === 404) {
    notFound()
  }
  
  if (!response.ok) {
    throw new Error(`Failed to fetch design: ${response.status} ${await response.text()}`)
  }

  return response.json() as Promise<DesignModel>
}

export default async function DesignDetailPage({
  params,
}: {
  params: Promise<{ design_id: string }>
}) {
  const { design_id } = await params
  const design = await fetchDesign(design_id)

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      {/* Header */}
      <div className="mb-4 sm:mb-6">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Layers className="h-6 w-6 text-primary" />
          <h1 className="text-xl sm:text-2xl font-bold">Design Details</h1>
        </div>
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        {/* 3D Viewer - First section like ComponentViewer */}
        <DesignViewer design={design} />

        {/* Design Details - Second section like ComponentDetailCard */}
        <DesignDetailCard design={design} />

        {/* Snapshot placements */}
        <Card>
          <CardHeader>
            <CardTitle>Snapshots in this Design</CardTitle>
            <CardDescription>
              Specific snapshot versions placed in this design assembly
            </CardDescription>
          </CardHeader>
          <div className="px-6 pb-4">
            <DesignPlacementList placements={design.components} />
          </div>
        </Card>
      </div>
    </div>
  )
}
