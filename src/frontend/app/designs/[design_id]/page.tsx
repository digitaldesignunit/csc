import { DesignModel } from '@/generated/DesignModel'
import { headers } from 'next/headers'
import { redirect, notFound } from 'next/navigation'
import DesignViewer from '@/components/designs/DesignViewer'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import Link from 'next/link'
import { getServerSession } from 'next-auth'
import DesignDetailCard from '@/components/designs/DesignDetailCard'

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
  const session = await getServerSession()
  
  const isOwner = session?.user?.id === design.creator
  const canEdit = isOwner || session?.user?.role === 'admin'

  return (
    <div className="grid gap-2 m-2">
      {/* 3D Viewer - First section like ComponentViewer */}
      <DesignViewer design={design} mode="reduced" />

      {/* Design Details - Second section like ComponentDetailCard */}
      <DesignDetailCard design={design} canEdit={canEdit} />

      {/* Component List */}
      <Card>
        <CardHeader>
          <CardTitle>Components in this Design</CardTitle>
          <CardDescription>
            List of all components used in this design assembly
          </CardDescription>
        </CardHeader>
        <div className="px-6 pb-4">
          <div className="space-y-2">
            {design.components.map((comp, index) => (
              <div key={comp.component} className="flex items-center justify-between p-3 border rounded-lg">
                <div className="flex items-center space-x-3">
                  <span className="text-sm text-muted-foreground">#{index + 1}</span>
                  <div>
                    <div className="font-small">{comp.component}</div>
                    <div className="text-sm text-muted-foreground">
                      o: [{comp.iframe.o.map(v => v.toFixed(2)).join(', ')}] <br />
                      x: [{comp.iframe.x.map(v => v.toFixed(2)).join(', ')}] <br />
                      y: [{comp.iframe.y.map(v => v.toFixed(2)).join(', ')}] <br />
                      z: [{comp.iframe.z.map(v => v.toFixed(2)).join(', ')}] <br />
                    </div>
                  </div>
                </div>
                <Link href={`/components/${comp.component}`}>
                  <Button variant="outline" size="sm">
                    View Component
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  )
}
