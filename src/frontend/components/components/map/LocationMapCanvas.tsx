'use client'

/**
 * The map of the Location Map page (decisions 8.170, 8.171): Leaflet with the
 * clustered pieces on the tiles of openstreetmap.de. Leaflet and its cluster
 * plugin are bundled from npm and loaded on the client only (they need
 * `window`), so the page renders on the server without them; the pins are
 * divIcons (no marker image files), the clusters are neutral with a count, the
 * pop-up of a click on an empty spot offers "Search near here".
 */
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import './location-map.css'

import { useEffect, useRef, useState } from 'react'
import type * as Leaflet from 'leaflet'

import type { LocationPoint } from '@/generated/CatalogModels'
import { ORIGINAL_FUNCTION_LABELS, vocabLabel } from '@/generated/Vocab'
import { OTHER_COLOR } from '@/lib/mapColors'
import { TILE_ATTRIBUTION, TILE_URL, boundsOf, clickedPointText } from '@/lib/locationMap'

type Props = {
  points: LocationPoint[]
  /** The colour of each point id (colour by, shared with the Similarity Map). */
  colors: Map<string, string>
  /** A click on a piece: the preview panel. */
  onPick: (id: string) => void
  /** The Browse link of "Search near here" for a clicked point. */
  searchLink: (lat: number, lon: number) => string
  /** Open a link of the app (no full page load). */
  onGo: (href: string) => void
  label: string
}

/** Where an empty map looks: central Europe. */
const DEFAULT_VIEW: [number, number] = [50.5, 10.5]
const DEFAULT_ZOOM = 5
const HEX = /^#[0-9a-f]{6}$/i

function pinColor(value: string | undefined): string {
  return value && HEX.test(value) ? value : OTHER_COLOR
}

/** What the hover label says of a piece, as an element (a name is text, never markup). */
function labelOf(point: LocationPoint): HTMLElement {
  const element = document.createElement('div')
  const name = document.createElement('strong')
  name.textContent = point.name || `Component #${point.catalog_number ?? ''}`.trim()
  element.append(name)
  const detail = [
    vocabLabel(ORIGINAL_FUNCTION_LABELS, point.original_function),
    point.catalog_number != null ? `#${point.catalog_number}` : null,
  ].filter(Boolean).join(' / ')
  if (detail) {
    const line = document.createElement('div')
    line.textContent = detail
    element.append(line)
  }
  return element
}

export default function LocationMapCanvas({ points, colors, onPick, searchLink, onGo, label }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const engine = useRef<{ L: typeof Leaflet; map: Leaflet.Map; cluster: Leaflet.MarkerClusterGroup } | null>(null)
  const [ready, setReady] = useState(false)
  // the handlers the map keeps are the latest ones
  const latest = useRef({ onPick, searchLink, onGo })
  useEffect(() => {
    latest.current = { onPick, searchLink, onGo }
  })

  // the map itself, once
  useEffect(() => {
    let cancelled = false
    let map: Leaflet.Map | null = null
    void (async () => {
      // the CommonJS object itself: the cluster plugin adds to the one it requires
      const L = ((await import('leaflet')) as unknown as { default: typeof Leaflet }).default
      await import('leaflet.markercluster')
      if (cancelled || !host.current) return
      map = L.map(host.current, { worldCopyJump: true, minZoom: 2, zoomSnap: 0.5 })
      map.setView(DEFAULT_VIEW, DEFAULT_ZOOM)
      L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map)
      const cluster = L.markerClusterGroup({
        showCoverageOnHover: false,
        maxClusterRadius: 48,
        chunkedLoading: true,
        iconCreateFunction: (group) => {
          const count = group.getChildCount()
          const size = count < 10 ? 36 : count < 100 ? 42 : 50
          const kind = count < 10 ? 's' : count < 100 ? 'm' : 'l'
          return L.divIcon({
            html: `<span>${count}</span>`,
            className: `csc-cluster csc-cluster-${kind}`,
            iconSize: [size, size],
          })
        },
      })
      map.addLayer(cluster)
      map.on('click', (event: Leaflet.LeafletMouseEvent) => {
        const { lat, lng } = event.latlng
        const link = latest.current.searchLink(lat, lng)
        const box = document.createElement('div')
        const where = document.createElement('div')
        where.className = 'csc-popup-coords'
        where.textContent = clickedPointText(lat, lng)
        const anchor = document.createElement('a')
        anchor.className = 'csc-popup-link'
        anchor.href = link
        anchor.textContent = 'Search near here'
        anchor.addEventListener('click', (e) => {
          e.preventDefault()
          latest.current.onGo(link)
        })
        box.append(where, anchor)
        L.popup({ className: 'csc-popup', closeButton: true, autoPan: true, minWidth: 150 })
          .setLatLng(event.latlng)
          .setContent(box)
          .openOn(map as Leaflet.Map)
      })
      engine.current = { L, map, cluster }
      setReady(true)
    })()
    return () => {
      cancelled = true
      engine.current = null
      setReady(false)
      map?.remove()
    }
  }, [])

  // the pieces, again when the points or the colouring change
  useEffect(() => {
    const current = engine.current
    if (!ready || !current) return
    const { L, cluster } = current
    cluster.clearLayers()
    const markers = points.map((point) => {
      const icon = L.divIcon({
        html: `<span style="background-color:${pinColor(colors.get(point.id))}"></span>`,
        className: 'csc-pin',
        iconSize: [20, 20],
      })
      const marker = L.marker([point.lat, point.lon], {
        icon,
        keyboard: true,
        alt: point.name || `Component ${point.catalog_number ?? ''}`.trim(),
      })
      marker.bindTooltip(labelOf(point), { direction: 'top', offset: [0, -8] })
      marker.on('click', () => latest.current.onPick(point.id))
      return marker
    })
    cluster.addLayers(markers)
  }, [ready, points, colors])

  // the map fits the points when they change (a filter, the layer), not when only the colours do
  useEffect(() => {
    const current = engine.current
    if (!ready || !current) return
    const bounds = boundsOf(points)
    if (bounds) current.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16, animate: false })
    else current.map.setView(DEFAULT_VIEW, DEFAULT_ZOOM, { animate: false })
  }, [ready, points])

  return <div ref={host} className="csc-map h-full w-full" role="application" aria-label={label} />
}
