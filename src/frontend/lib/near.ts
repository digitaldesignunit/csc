/**
 * The "Near" search of Browse (decisions 8.170, 8.173): which pieces are near
 * a point, nearest first, on the current place of a piece or on its origin.
 * The state is four URL parameters that the backend list and count take
 * unchanged: `near_lat`, `near_lon`, `near_layer` (current | origin; current
 * is not written) and `radius_km` (empty = the nearest first, without a
 * limit). The parts that read and build them, read a pasted "lat, lon", and
 * word a distance are pure and tested; the filter bar and the table only call
 * them.
 */
import type { ParamsLike } from '@/lib/browse'
import type { CatalogRow } from '@/generated/CatalogModels'

export const NEAR_LAYERS = ['current', 'origin'] as const
export type NearLayer = (typeof NEAR_LAYERS)[number]

export const NEAR_KEYS = ['near_lat', 'near_lon', 'near_layer', 'radius_km'] as const
export const DEFAULT_LAYER: NearLayer = 'current'

export const NEAR_LAYER_LABELS: Record<NearLayer, string> = {
  current: 'Current',
  origin: 'Origin',
}

export const NEAR_HELP =
  'Paste a point as "latitude, longitude" (for example 49.8728, 8.6512, as a map shows it). '
  + 'Current measures where an element is now; Origin measures the building it comes from, which is '
  + 'known for fewer elements. With a radius in km only the elements within it are listed; without one '
  + 'every element with a known place is listed, nearest first. Elements without a known place on the '
  + 'chosen layer are left out.'

export type NearQuery = {
  lat: number
  lon: number
  layer: NearLayer
  /** In km; null = no limit. */
  radiusKm: number | null
}

const NUMBER = /^[+-]?\d+(?:\.\d+)?$/

/** One coordinate as typed: a plain decimal number inside the range, else null. */
export function parseCoordinate(text: string | null | undefined, axis: 'lat' | 'lon'): number | null {
  const value = (text ?? '').trim().replace(/\u00b0$/, '').trim()
  if (!NUMBER.test(value)) return null
  const number = Number(value)
  const limit = axis === 'lat' ? 90 : 180
  return Math.abs(number) <= limit ? number : null
}

/** A pasted "49.8728, 8.6512" -> {lat, lon}, or null. The pair may be
 *  separated by a comma, a semicolon or spaces (any number of them), wrapped
 *  in brackets, and carry degree signs, as a map or a spreadsheet gives it. */
export function parseLatLon(text: string | null | undefined): { lat: number; lon: number } | null {
  const bare = (text ?? '').trim().replace(/^[([{]\s*/, '').replace(/\s*[)\]}]$/, '')
  const parts = bare.split(/\s*[,;]\s*|\s+/).filter((p) => p !== '')
  if (parts.length !== 2) return null
  const lat = parseCoordinate(parts[0], 'lat')
  const lon = parseCoordinate(parts[1], 'lon')
  return lat === null || lon === null ? null : { lat, lon }
}

/** A coordinate for a URL or a box: at most 6 decimals (about 10 cm), no tail of zeros. */
export function coordinateText(value: number): string {
  return String(Number(value.toFixed(6)))
}

/** The texts of the two coordinate boxes for a stored location (empty without
 *  one): plain decimals through `coordinateText`, never an exponent, so what
 *  the form shows is what `locationFromBoxes` reads back ("1e-7" would be
 *  refused: a coordinate that small shows as "0"). */
export function boxesOfLocation(
  location: { lat: number; lon: number } | null | undefined,
): { lat: string; lon: string } {
  return location ? { lat: coordinateText(location.lat), lon: coordinateText(location.lon) } : { lat: '', lon: '' }
}

/** "49.8728, 8.6512": the pair as the point field shows it. */
export function latLonText(lat: number, lon: number): string {
  return `${coordinateText(lat)}, ${coordinateText(lon)}`
}

/** The radius in km: a number above 0, else null. */
export function parseRadius(text: string | null | undefined): number | null {
  const value = (text ?? '').trim()
  if (!/^\d+(?:\.\d+)?$/.test(value)) return null
  const number = Number(value)
  return number > 0 && number <= 100_000 ? number : null
}

/** The near search of the URL, or null when there is none or it cannot be used
 *  (then it is ignored, not sent: the backend would answer 422). A radius that
 *  cannot be used is left out and the search stays. */
export function parseNear(params: ParamsLike): NearQuery | null {
  const lat = parseCoordinate(params.get('near_lat'), 'lat')
  const lon = parseCoordinate(params.get('near_lon'), 'lon')
  if (lat === null || lon === null) return null
  const layer = (NEAR_LAYERS as readonly string[]).includes(params.get('near_layer') ?? '')
    ? (params.get('near_layer') as NearLayer)
    : DEFAULT_LAYER
  return { lat, lon, layer, radiusKm: parseRadius(params.get('radius_km')) }
}

/** The parameters for the backend list and count (empty without a usable search). */
export function nearBackendParams(params: ParamsLike): Record<string, string> {
  const near = parseNear(params)
  if (!near) return {}
  return {
    near_lat: coordinateText(near.lat),
    near_lon: coordinateText(near.lon),
    near_layer: near.layer,
    ...(near.radiusKm !== null ? { radius_km: String(near.radiusKm) } : {}),
  }
}

/** The URL changes that set a near search (null values remove); the default
 *  layer is not written. `wasActive` says whether a search was already in the
 *  URL: one that starts or ends also resets the sort, so an earlier explicit
 *  sort does not beat the distance of a fresh search and `distance` never
 *  outlives its search. Changing a search that is active keeps the sort. */
export function nearChanges(near: NearQuery | null, wasActive = false): Record<string, string | null> {
  const sort: Record<string, null> = !near || !wasActive ? { sortkey: null, sortorder: null } : {}
  if (!near) return { near_lat: null, near_lon: null, near_layer: null, radius_km: null, ...sort }
  return {
    ...sort,
    near_lat: coordinateText(near.lat),
    near_lon: coordinateText(near.lon),
    near_layer: near.layer === DEFAULT_LAYER ? null : near.layer,
    radius_km: near.radiusKm !== null ? String(near.radiusKm) : null,
  }
}

/** The chip of an active search: "Near 49.8728, 8.6512 (current, within 50 km)". */
export function nearChipLabel(near: NearQuery): string {
  const where = near.layer === 'origin' ? 'origin' : 'current'
  const radius = near.radiusKm !== null ? `, within ${near.radiusKm} km` : ''
  return `Near ${latLonText(near.lat, near.lon)} (${where}${radius})`
}

/** A stored place: two finite numbers inside the range of a latitude and a longitude. */
function onGlobe(place: { lat: number; lon: number }): boolean {
  return Number.isFinite(place.lat) && Number.isFinite(place.lon)
    && Math.abs(place.lat) <= 90 && Math.abs(place.lon) <= 180
}

/** The Browse link of "Near this piece": the current place of the piece, else
 *  its origin place, else null (the link is hidden). */
export function nearThisPieceLink(
  location: { lat: number; lon: number } | null | undefined,
  originLocation: { lat: number; lon: number } | null | undefined,
): string | null {
  const usable = (place: { lat: number; lon: number } | null | undefined) => place != null && onGlobe(place)
  const [place, layer] = usable(location) ? [location, 'current'] : usable(originLocation) ? [originLocation, 'origin'] : [null, '']
  if (!place) return null
  const query = new URLSearchParams({ near_lat: coordinateText(place.lat), near_lon: coordinateText(place.lon) })
  if (layer === 'origin') query.set('near_layer', 'origin')
  return `/components?${query.toString()}`
}

// A ROW'S DISTANCE --------------------------------------------------------------
/** The distance of a list row in metres, or null (a list without a near search carries none). */
export function rowDistance(row: Pick<CatalogRow, 'distance_m'> | null | undefined): number | null {
  const metres = row?.distance_m
  return typeof metres === 'number' && Number.isFinite(metres) && metres >= 0 ? metres : null
}

/** "850 m" under 1 km, else km with one decimal: "26.5 km", "443.7 km". */
export function distanceText(metres: number): string {
  if (metres < 999.5) return `${Math.round(metres)} m`
  return `${(metres / 1000).toFixed(1)} km`
}

// A PLACE'S COORDINATES IN A FORM -----------------------------------------------
export type PlaceLocation = { lat: number; lon: number }

/** What a form holds while the two coordinate boxes do not make a point (one
 *  empty, or a text that is no number on the globe): it cannot be saved, and
 *  it is not the old point, which would be saved without a word. */
export const INVALID_LOCATION: PlaceLocation = { lat: Number.NaN, lon: Number.NaN }

export const LOCATION_PROBLEM =
  'Latitude (-90 to 90) and longitude (-180 to 180) need a number each, or both empty.'

/** The two boxes as typed -> the point they make (null = both empty, no
 *  location), or the problem with them. */
export function locationFromBoxes(
  latText: string,
  lonText: string,
): { location: PlaceLocation | null; problem: string | null } {
  if (latText.trim() === '' && lonText.trim() === '') return { location: null, problem: null }
  const lat = parseCoordinate(latText, 'lat')
  const lon = parseCoordinate(lonText, 'lon')
  if (lat === null || lon === null) return { location: null, problem: LOCATION_PROBLEM }
  return { location: { lat, lon }, problem: null }
}

/** Why a form's place location cannot be saved, or null (none, or a good point). */
export function locationProblem(location: PlaceLocation | null | undefined): string | null {
  if (!location) return null
  return onGlobe(location) ? null : LOCATION_PROBLEM
}

export type LatLonBoxes = { lat: string; lon: string }

/** A pair of coordinates in a text ("49.8728, 8.6512" and the other forms
 *  `parseLatLon` reads) as the two boxes' texts, or null. */
export function pairFromText(text: string | null | undefined): LatLonBoxes | null {
  const point = parseLatLon(text)
  return point ? { lat: coordinateText(point.lat), lon: coordinateText(point.lon) } : null
}

// a number and then the separator, as when a pair is typed into the latitude box
const NUMBER_THEN_COMMA = /^\s*([+-]?\d+(?:\.\d*)?)\s*[,;]\s*$/

/** The two coordinate boxes of a location form after the text of one of them
 *  changed to `value` (a typed character, a paste, an autofill):
 *  - a text that reads as a pair ("49.8728, 8.6512", pasted or filled in whole)
 *    fills both boxes, whichever box it went into; one typed character never
 *    does (a space typed between two numbers would split the box on the way);
 *  - a number followed by a comma typed in the latitude box stays the latitude
 *    and asks for the focus to move to the longitude box (`focus: 'lon'`), the
 *    comma is not inserted: typing "49.8728, 8.6512" goes lat, comma, lon;
 *  - anything else (a single number, a half-typed text) is the box's text as
 *    typed, leading spaces dropped from the longitude. A decimal comma is not
 *    supported: the comma is the separator. */
export function latLonEdit(
  box: 'lat' | 'lon',
  current: LatLonBoxes,
  value: string,
): { boxes: LatLonBoxes; focus: 'lon' | null } {
  const typedOne = value.length === current[box].length + 1
  const pair = typedOne ? null : pairFromText(value)
  if (pair) return { boxes: pair, focus: null }
  if (box === 'lat') {
    const found = NUMBER_THEN_COMMA.exec(value)
    if (found) return { boxes: { ...current, lat: found[1] }, focus: 'lon' }
    return { boxes: { ...current, lat: value }, focus: null }
  }
  return { boxes: { ...current, lon: value.replace(/^\s+/, '') }, focus: null }
}

/** The origin's place location of a form, as its problem. */
export function originLocationProblem(
  origin: { place?: { location?: PlaceLocation | null } | null } | null | undefined,
): string | null {
  return locationProblem(origin?.place?.location)
}
