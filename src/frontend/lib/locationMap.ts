/**
 * The pure parts of the Location Map page (decisions 8.170, 8.171): the layer
 * in the URL, the parameters the backend takes, the links to Browse ("Show as
 * list", "Search near here"), the box the map fits, and the words about the
 * pieces that have no point. The state of the page is the URL, so a link
 * carries the filters, the circulation, a fit or near search and the layer.
 */
import { FILTER_KEYS, parseCirculation, withParams, type ParamsLike } from '@/lib/browse'
import { fitBackendParams } from '@/lib/fit'
import { MAP_TILE_ORIGIN } from '@/lib/csp'
import { coordinateText, nearBackendParams, nearChanges } from '@/lib/near'

export const MAP_LAYERS = ['current', 'origin'] as const
export type MapLayer = (typeof MAP_LAYERS)[number]
export const DEFAULT_MAP_LAYER: MapLayer = 'current'

export const MAP_LAYER_LABELS: Record<MapLayer, string> = {
  current: 'Current',
  origin: 'Origin',
}

/** What each layer shows, for the help text and the empty message. */
export const MAP_LAYER_NOUNS: Record<MapLayer, string> = {
  current: 'current location',
  origin: 'origin location',
}

/** The tiles and who is named for them (decision 8.171). Only the Location Map loads them. */
export const TILE_HOST = MAP_TILE_ORIGIN
export const TILE_URL = `${TILE_HOST}/{z}/{x}/{y}.png`
export const TILE_ATTRIBUTION =
  '(c) <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'
  + ', tiles by <a href="https://fossgis.de" target="_blank" rel="noopener noreferrer">FOSSGIS e.V.</a>'

/** The layer of the URL: origin when it says so, else the current one. */
export function parseLayer(params: ParamsLike): MapLayer {
  return params.get('layer') === 'origin' ? 'origin' : DEFAULT_MAP_LAYER
}

/** The URL change that sets a layer; Current is the default and is not written. */
export function layerChanges(layer: MapLayer): Record<string, string | null> {
  return { layer: layer === DEFAULT_MAP_LAYER ? null : layer }
}

/** The query for `GET /identities/locations`: the circulation, the filters of
 *  Browse, the search text, a usable fit or near search, and the layer. */
export function locationsBackendParams(params: ParamsLike): URLSearchParams {
  const out = new URLSearchParams({ circulation: parseCirculation(params.get('circulation')) })
  for (const key of [...FILTER_KEYS, 'q']) {
    const value = params.get(key)
    if (value) out.set(key, value)
  }
  const searches = new URLSearchParams(params.toString())
  for (const [key, value] of Object.entries({ ...fitBackendParams(searches), ...nearBackendParams(searches) })) {
    out.set(key, value)
  }
  out.set('layer', parseLayer(params))
  return out
}

/** The Browse link with the same filters ("Show as list"): everything the
 *  page keeps in the URL except the layer, which Browse has no use for. */
export function showAsListLink(params: ParamsLike): string {
  const next = new URLSearchParams(params.toString())
  next.delete('layer')
  next.delete('page')
  const text = next.toString()
  return text ? `/components?${text}` : '/components'
}

/** The Browse link of "Search near here": the filters stay, the point is the
 *  clicked one on the layer being shown, nearest first (no radius). An earlier
 *  near search, radius and sort of the page are replaced. */
export function searchNearHereLink(params: ParamsLike, lat: number, lon: number, layer: MapLayer): string {
  const base = new URLSearchParams(params.toString())
  base.delete('layer')
  const next = withParams(base, {
    ...nearChanges({ lat: clampLat(lat), lon: wrapLon(lon), layer, radiusKm: null }, false),
  })
  return `/components?${next.toString()}`
}

/** A latitude inside -90..90 (the map can be dragged beyond the poles). */
export function clampLat(lat: number): number {
  return Math.max(-90, Math.min(90, Number(coordinateText(lat))))
}

/** A longitude inside -180..180: the map repeats east and west, a click on
 *  the next world is the same place. */
export function wrapLon(lon: number): number {
  const wrapped = ((((lon + 180) % 360) + 360) % 360) - 180
  return Number(coordinateText(wrapped))
}

/** The coordinates a click shows in its popup: the same point that "Search near
 *  here" searches (latitude clamped, longitude wrapped), as "lat, lon". */
export function clickedPointText(lat: number, lon: number): string {
  return `${coordinateText(clampLat(lat))}, ${coordinateText(wrapLon(lon))}`
}

export type Bounds = [[number, number], [number, number]]

/** The south-west and north-east corners around some points, or null without
 *  points. One point, or points on one spot (the usual case: hundreds of pieces
 *  share a site), get a box of about 1 km around them so the map zooms to the
 *  site and not to the highest zoom. */
export function boundsOf(points: readonly { lat: number; lon: number }[]): Bounds | null {
  if (points.length === 0) return null
  let south = Infinity
  let north = -Infinity
  let west = Infinity
  let east = -Infinity
  for (const p of points) {
    south = Math.min(south, p.lat)
    north = Math.max(north, p.lat)
    west = Math.min(west, p.lon)
    east = Math.max(east, p.lon)
  }
  const MIN_SPAN = 0.01 // degrees, about 1 km
  if (north - south < MIN_SPAN) {
    const middle = (north + south) / 2
    south = middle - MIN_SPAN / 2
    north = middle + MIN_SPAN / 2
  }
  if (east - west < MIN_SPAN) {
    const middle = (east + west) / 2
    west = middle - MIN_SPAN / 2
    east = middle + MIN_SPAN / 2
  }
  return [[south, west], [north, east]]
}

/** What the page says about the pieces: how many are on the map, and how many
 *  have no point on the layer. */
export function mapCountText(
  layer: MapLayer,
  counts: { total: number; displayed: number; left_out: number },
): string {
  const noun = MAP_LAYER_NOUNS[layer]
  const piece = (n: number) => (n === 1 ? 'piece' : 'pieces')
  if (counts.total === 0) return 'No pieces match the filters.'
  if (counts.displayed === 0) {
    const article = layer === 'origin' ? 'an' : 'a'
    return `None of the ${counts.total} ${piece(counts.total)} has ${article} ${noun} to show.`
  }
  const shown = `${counts.displayed} ${piece(counts.displayed)} on the map`
  if (counts.left_out === 0) return shown
  return `${shown}; ${counts.left_out} ${counts.left_out === 1 ? 'has' : 'have'} no ${noun}.`
}

/** The plain message of an empty layer (above the map). */
export function emptyLayerText(layer: MapLayer, total: number): string {
  if (total === 0) return 'No pieces match the filters. Change or remove a filter.'
  return layer === 'origin'
    ? 'No piece has an origin location yet. It is set in Edit provenance on the component page. Switch to Current to see where the pieces are now.'
    : 'No piece has a current location. Add one in Edit details on the component page.'
}
