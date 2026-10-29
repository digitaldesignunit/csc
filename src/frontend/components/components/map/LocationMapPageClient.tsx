'use client'

/**
 * The Location Map (decisions 8.170, 8.171): every piece the caller may see on
 * a map, as the current or the origin location, clustered, coloured like the
 * Similarity Map, with the filter bar of Browse. The state is the URL: the
 * filters, the circulation, a fit or near search and the layer, so a link
 * carries them and "Show as list" opens Browse with the same ones.
 */
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { List, Loader2, SlidersHorizontal } from 'lucide-react'

import CatalogFilterBar from '@/components/catalog/CatalogFilterBar'
import { PreviewProvider, usePreview } from '@/components/components/preview/ComponentPreview'
import { Button } from '@/components/ui/button'
import Help from '@/components/ui/help'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { LocationMap } from '@/generated/CatalogModels'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import {
  CIRCULATION_GROUPS,
  CIRCULATION_HELP,
  IN_CIRCULATION_PARTS,
  activeFilters,
  circulationGroup,
  parseCirculation,
  withParams,
} from '@/lib/browse'
import { parseFit } from '@/lib/fit'
import { useMaterials } from '@/lib/lineage'
import {
  MAP_LAYERS,
  MAP_LAYER_LABELS,
  emptyLayerText,
  layerChanges,
  locationsBackendParams,
  mapCountText,
  parseLayer,
  searchNearHereLink,
  showAsListLink,
  type MapLayer,
} from '@/lib/locationMap'
import { COLOR_BY_OPTIONS, colorMap, legendOf, type ColorBy } from '@/lib/mapColors'
import { parseNear } from '@/lib/near'
import { cn } from '@/lib/utils'
import LocationMapCanvas from './LocationMapCanvas'

const MAP_HELP =
  'Every element you may see, as a point on the map. Current is where an element is now; Origin is the building it '
  + 'comes from, known for fewer elements. Elements at one place are grouped: click a group to zoom in. Click a '
  + 'element to preview it, or an empty spot to search near it. The filters are those of Browse.'

/** The map and its preview: a click on a piece opens the shared preview panel. */
function MapWithPreview(props: Omit<React.ComponentProps<typeof LocationMapCanvas>, 'onPick'>) {
  const preview = usePreview()
  return <LocationMapCanvas {...props} onPick={(id) => preview?.open(id)} />
}

export default function LocationMapPageClient() {
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const materials = useMaterials(true)
  const [colorBy, setColorBy] = useState<ColorBy>('shape_class')
  const [data, setData] = useState<LocationMap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const wide = useMediaQuery('(min-width: 768px)')
  // on a phone the filters fold away so the map gets the screen
  const [filtersOpen, setFiltersOpen] = useState(false)

  const layer = parseLayer(search)
  const circulation = parseCirculation(search.get('circulation'))
  const group = circulationGroup(circulation)
  // what the backend is asked: the same text while the URL says the same
  const query = locationsBackendParams(search).toString()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetch(`/api/backend/identities/locations?${query}`, {
      cache: 'no-store',
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`The location map could not be loaded (${res.status}).`)
        return (await res.json()) as LocationMap
      })
      .then((json) => {
        setData(json)
        setLoading(false)
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return
        setError(err.message)
        setLoading(false)
      })
    return () => controller.abort()
  }, [query])

  const go = (changes: Record<string, string | null>) => {
    const next = withParams(new URLSearchParams(search.toString()), changes)
    const text = next.toString()
    router.replace(text ? `${pathname}?${text}` : pathname)
  }

  const materialLabel = useMemo(() => {
    const byId = new Map(materials.map((m) => [m._id, m.label]))
    return (id: string) => byId.get(id) ?? id
  }, [materials])
  const points = useMemo(() => data?.points ?? [], [data])
  const legend = useMemo(() => legendOf(points, colorBy, { material: materialLabel }), [points, colorBy, materialLabel])
  const colors = useMemo(() => colorMap(points, colorBy), [points, colorBy])
  const previewItems = useMemo(
    () => points.map((p) => ({ id: p.id, name: p.name, number: p.catalog_number, dataset: p.dataset })),
    [points],
  )

  const showLayer: MapLayer = data?.layer ?? layer
  const empty = !loading && data !== null && data.displayed === 0
  const status = error
    ?? (loading && !data ? '' : data ? mapCountText(showLayer, data) : '')

  const circulationControls = (
    <div className="flex flex-wrap items-center gap-2">
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={group}
        onValueChange={(value) => {
          const target = CIRCULATION_GROUPS.find((g) => g.group === value)
          if (target) go({ circulation: target.value === 'active' ? null : target.value })
        }}
        aria-label="Circulation"
      >
        {CIRCULATION_GROUPS.map((g) => (
          <ToggleGroupItem key={g.group} value={g.group} className="px-3 text-xs sm:text-sm">
            {g.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <Help label="Circulation" text={CIRCULATION_HELP} />
      {group === 'in' && (
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={circulation}
          onValueChange={(value) => {
            if (value) go({ circulation: value === 'active' ? null : value })
          }}
          aria-label="In place or not"
        >
          {IN_CIRCULATION_PARTS.map((part) => (
            <ToggleGroupItem key={part.value} value={part.value} className="px-2.5 text-xs">
              {part.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
    </div>
  )
  const filterCount = activeFilters(search).length + (parseFit(search) ? 1 : 0) + (parseNear(search) ? 1 : 0)
    + (circulation !== 'active' ? 1 : 0)
  const showFilters = wide || filtersOpen

  return (
    <PreviewProvider items={previewItems}>
      <div className="flex w-full max-w-full flex-col gap-2 overflow-x-hidden p-3 md:h-[calc(100dvh-3.5rem)] md:min-h-0">
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={layer}
            onValueChange={(value) => {
              if (value) go(layerChanges(value as MapLayer))
            }}
            aria-label="Which location"
          >
            {MAP_LAYERS.map((item) => (
              <ToggleGroupItem key={item} value={item} className="px-3 text-xs sm:text-sm">
                {MAP_LAYER_LABELS[item]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {wide && circulationControls}
          {!wide && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((open) => !open)}
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Filters
              {filterCount > 0 && (
                <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{filterCount}</span>
              )}
            </Button>
          )}
          <Button asChild variant="outline" size="sm" className="ml-auto gap-1.5">
            <Link href={showAsListLink(search)} aria-label="Show as list">
              <List className="h-4 w-4" aria-hidden />
              <span className="hidden min-[420px]:inline">Show as list</span>
            </Link>
          </Button>
        </div>

        {showFilters && (
          <div className="space-y-2">
            {!wide && circulationControls}
            <CatalogFilterBar circulation={circulation} withFit withNear />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Select value={colorBy} onValueChange={(value) => setColorBy(value as ColorBy)}>
            <SelectTrigger className="h-8 w-[170px]" aria-label="Colour by">
              <SelectValue placeholder="Colour by" />
            </SelectTrigger>
            <SelectContent>
              {COLOR_BY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>Colour: {o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex min-w-0 items-center gap-1 text-sm text-muted-foreground">
            {loading ? (
              <span className="inline-flex items-center gap-1 text-xs">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                Loading the map...
              </span>
            ) : (
              <span aria-live="polite" className={cn(error && 'text-destructive')}>{status}</span>
            )}
            <Help label="About the location map" text={MAP_HELP} />
          </div>
        </div>

        {legend.length > 0 && (
          <ul className="flex max-h-16 flex-wrap gap-x-3 gap-y-1 overflow-y-auto text-xs" aria-label="Legend">
            {legend.map((entry) => (
              <li key={entry.key} className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full border" style={{ backgroundColor: entry.color }} aria-hidden />
                <span>{entry.label}</span>
                <span className="text-muted-foreground">{entry.count}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="relative h-[max(320px,calc(100dvh-17rem))] w-full overflow-hidden rounded-md border md:h-auto md:min-h-0 md:flex-1">
          <MapWithPreview
            points={points}
            colors={colors}
            searchLink={(lat, lon) => searchNearHereLink(search, lat, lon, showLayer)}
            onGo={(href) => router.push(href)}
            label={`Location map, ${MAP_LAYER_LABELS[showLayer].toLowerCase()} locations`}
          />
          {empty && (
            <div className="pointer-events-none absolute inset-x-0 top-3 z-[1000] flex justify-center px-3">
              <p className="pointer-events-auto max-w-md rounded-md border bg-card/95 px-3 py-2 text-center text-sm text-card-foreground shadow-sm">
                {emptyLayerText(showLayer, data?.total ?? 0)}
              </p>
            </div>
          )}
        </div>
      </div>
    </PreviewProvider>
  )
}
