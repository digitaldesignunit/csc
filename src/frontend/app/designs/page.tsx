import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { DesignModel } from '@/generated/DesignModel'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import Link from 'next/link'
import { formatTimestamp } from '@/lib/utils'
import { Package, ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SearchParams = {
  page?: string
  size?: string
}

async function fetchDesigns({
  page,
  size,
}: {
  page: number
  size: number
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const listParams = new URLSearchParams({
    page: String(page),
    size: String(size),
  })

  const fetchOpts = { cache: 'no-store' as const, headers: { cookie } }

  const itemsRes = await fetch(
    `${base}/api/backend/designs?${listParams.toString()}`,
    fetchOpts
  )

  if (itemsRes.status === 401) {
    redirect('/auth/signin?callbackUrl=/designs')
  }
  if (!itemsRes.ok) {
    throw new Error(`Failed to fetch designs: ${itemsRes.status} ${await itemsRes.text()}`)
  }

  const items = (await itemsRes.json()) as DesignModel[]
  return { items }
}

export default async function DesignsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams

  const page = Number(sp?.page ?? 1)
  const size = Number(sp?.size ?? 20)

  const { items } = await fetchDesigns({ page, size })

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Package className="h-6 w-6 sm:h-8 sm:w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Designs</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Browse and explore design assemblies created by the community
        </p>
      </div>

      {/* Design Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">{items.length}</div>
            <p className="text-xs text-muted-foreground">Designs</p>
          </div>
        </Card>
        
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">
              {items.reduce((sum, design) => sum + (design.components?.length || 0), 0)}
            </div>
            <p className="text-xs text-muted-foreground">Components</p>
          </div>
        </Card>
        
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">
              {items.reduce((sum, design) => sum + (design.additional_geometry?.length || 0), 0)}
            </div>
            <p className="text-xs text-muted-foreground">Additional Geometries</p>
          </div>
        </Card>
        
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">
              {items.length > 0 
                ? Math.round(items.reduce((sum, design) => sum + (design.components?.length || 0), 0) / items.length)
                : 0
              }
            </div>
            <p className="text-xs text-muted-foreground">Avg. Components/Design</p>
          </div>
        </Card>
      </div>

      <div className="grid gap-6">
        {/* Design Overview Section */}
        <Card>
          <CardHeader>
            {/* No create new design button for now */}
            {/* <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <Link href="/designs/create">
                <Button className="w-full sm:w-auto">
                  <Plus className="h-4 w-4 mr-2" />
                  Create New Design
                </Button>
              </Link>
            </div> */}
          </CardHeader>
          <CardContent>
            {items.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Package className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                <p className="text-lg font-medium">No designs yet</p>
                <p>Be the first to create a design assembly!</p>
              </div>
            ) : (
              <div className="space-y-4">                
                <div className="grid gap-4">
                  {items.map((design) => (
                    <DesignCard key={design._id} design={design} />
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function DesignCard({ design }: { design: DesignModel }) {
  const designId = design._id
  const componentCount = Array.isArray(design.components) ? design.components.length : 0
  const addGeomCount = Array.isArray(design.additional_geometry) ? design.additional_geometry.length : 0

  return (
    <div className="border rounded-lg hover:bg-muted/50 transition-colors">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between p-4 gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <h3 className="font-medium text-base truncate">
              {String(design.name ?? 'Unnamed Design')}
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <Badge className="text-xs">
              {componentCount} component{componentCount !== 1 ? 's' : ''}
            </Badge>
            <Badge variant="secondary"className="text-xs">
              {addGeomCount} add. geom.
            </Badge>
          </div>
          <div className="text-xs sm:text-sm text-muted-foreground space-y-1">
            <p className="line-clamp-2">
              <strong>{String(design.description ?? 'No description provided')}</strong>
            </p>
            <p className="break-all">
              ID: <Link 
                href={`/designs/${design._id}`}
                className="text-primary hover:text-primary/80 hover:underline inline-flex items-center gap-1 transition-colors"
              >
                {design._id}
                <ExternalLink className="h-3 w-3" />
              </Link>
            </p>
            <p>
              Created by: {('creator_username' in design && typeof (design as Record<string, unknown>).creator_username === 'string')
                ? String((design as Record<string, unknown>).creator_username)
                : 'Unknown'}
            </p>
            <p>Created: {formatTimestamp(design.created)}</p>
            <p>Modified: {formatTimestamp(design.lastmodified)}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2 lg:ml-4 lg:flex-shrink-0">
          <Link href={`/designs/${designId}`}>
            <Button variant="outline" size="sm" className="w-full sm:w-auto">
              <ExternalLink className="h-4 w-4 mr-2" />
              View Design
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}