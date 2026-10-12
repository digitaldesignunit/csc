/**
 * The layout of the swimlane graph (decision 8.140): the piece in the middle
 * lane, parents above, children below; a time axis in sections by year (by
 * month where a year is dense), not to scale, undated events first; events of
 * one day line up across the lanes, so a cut link falls on the child's first
 * version. Pure: no DOM, the component draws what this returns.
 */
import {
  EVIDENCE_METHOD_LABELS,
  EXIT_KIND_LABELS,
  ORIGIN_KIND_LABELS,
  vocabLabel,
} from '@/generated/Vocab'
import type {
  HistoryEvent,
  HistoryLane,
  HistoryLayers,
  HistoryLink,
  HistoryResponse,
} from '@/lib/history/types'
import { formatDay } from '@/lib/utils'

export const GEOMETRY = {
  rowHeight: 66,
  colPad: 20,
  eventWidth: 30,
  sectionHeight: 22,
  monthHeight: 18,
  margin: 14,
  footer: 26,
}

/** a year with more event days than this is cut into months */
export const DENSE_COLUMNS = 8

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const KIND_ORDER: Record<string, number> = {
  origin: 0, version: 1, evidence_group: 2, evidence: 2, exit: 3, withdrawal: 4,
}

/** The day of an event, `YYYY-MM-DD`; empty when it has no date. */
export function dayKey(at: string | null | undefined): string {
  return at ? String(at).slice(0, 10) : ''
}

/** The key of an evidence group in a lane: lane, day and method. */
export function groupKey(laneId: string, event: HistoryEvent): string {
  return `${laneId}|${event.day ?? dayKey(event.at)}|${event.method ?? ''}`
}

// LAYERS AND GROUPS -----------------------------------------------------------
/** The layers of the History card: Lineage off leaves the piece alone, States
 *  off drops the versions, Evidence off the evidence events. */
export function applyLayers(history: HistoryResponse, layers: HistoryLayers): HistoryResponse {
  const lanes = history.lanes
    .filter((lane) => layers.lineage || lane.role === 'piece')
    .map((lane) => ({
      ...lane,
      events: lane.events?.filter((event) => {
        if (event.kind === 'version') return layers.states
        if (event.kind === 'evidence_group' || event.kind === 'evidence') return layers.evidence
        return true
      }),
    }))
  return { ...history, lanes, links: layers.lineage ? history.links : [], more: layers.lineage ? history.more : 0 }
}

/** Evidence groups opened into their records. A group whose records are not
 *  at hand (not loaded yet) stays a group. */
export function expandGroups(
  history: HistoryResponse,
  expanded: ReadonlySet<string> | 'all',
  records: ReadonlyMap<string, HistoryEvent>,
): HistoryResponse {
  const lanes = history.lanes.map((lane) => {
    if (!lane.events) return lane
    const events: HistoryEvent[] = []
    for (const event of lane.events) {
      const key = event.kind === 'evidence_group' ? groupKey(lane.id, event) : null
      const open = key !== null && (expanded === 'all' || expanded.has(key))
      const found = open ? (event.ids ?? []).map((id) => records.get(id)) : []
      if (open && found.length > 0 && found.every(Boolean)) {
        for (const record of found as HistoryEvent[]) events.push({ ...record, groupKey: key as string })
      } else {
        events.push(event)
      }
    }
    return { ...lane, events }
  })
  return { ...history, lanes }
}

// DESCRIPTIONS ----------------------------------------------------------------
export type Glyph = 'origin' | 'version' | 'version-corrected' | 'group' | 'record' | 'exit' | 'withdrawal'

export function glyphOf(event: HistoryEvent): Glyph {
  switch (event.kind) {
    case 'origin': return 'origin'
    case 'version': return event.corrected ? 'version-corrected' : 'version'
    case 'evidence_group': return 'group'
    case 'evidence': return 'record'
    case 'exit': return 'exit'
    default: return 'withdrawal'
  }
}

export function describeEvent(event: HistoryEvent): { title: string; lines: string[]; short: string } {
  const when = event.at ? formatDay(String(event.at), event.precision) : 'date unknown'
  const lines = [when]
  const later = event.cycle != null ? ' (earlier cycle)' : ''
  switch (event.kind) {
    case 'origin':
      return {
        title: event.planned
          ? `In place: ${event.detail === 'demolition' ? 'demolition' : 'deinstallation'} planned`
          : `Entered circulation${event.detail ? `: ${vocabLabel(ORIGIN_KIND_LABELS, event.detail)}` : ''}${later}`,
        lines, short: 'start',
      }
    case 'version': {
      const notes = [
        event.status && event.status !== 'published' ? event.status : null,
        event.corrected ? 'replaced by a correction' : null,
        event.corrects ? 'a correction' : null,
        event.withdrawn ? 'withdrawn' : null,
      ].filter(Boolean) as string[]
      if (event.name) lines.unshift(event.name)
      if (notes.length) lines.push(notes.join(', '))
      return { title: `Version v${event.version ?? '?'}`, lines, short: `v${event.version ?? '?'}` }
    }
    case 'evidence_group': {
      const count = event.count ?? event.ids?.length ?? 0
      return {
        title: `${count} ${count === 1 ? 'record' : 'records'}: ${vocabLabel(EVIDENCE_METHOD_LABELS, event.method ?? '')}`,
        lines: [...lines, 'Click to open the records'], short: String(count),
      }
    }
    case 'evidence':
      return {
        title: vocabLabel(EVIDENCE_METHOD_LABELS, event.method ?? ''),
        lines: [
          ...(event.quantity ? [event.quantity.replace(/_/g, ' ')] : []),
          ...lines,
          ...(event.status && event.status !== 'published' ? [event.status] : []),
          ...(event.corrected ? ['replaced by a correction'] : []),
        ],
        short: '',
      }
    case 'exit':
      return {
        title: `Left circulation${event.detail ? `: ${vocabLabel(EXIT_KIND_LABELS, event.detail)}` : ''}${later}`,
        lines, short: 'exit',
      }
    default:
      return { title: 'Withdrawn', lines, short: 'withdrawn' }
  }
}

// LAYOUT ----------------------------------------------------------------------
export type PlacedEvent = {
  key: string
  lane: number
  laneId: string
  event: HistoryEvent
  x: number
  y: number
}

export type PlacedLink = {
  key: string
  link: HistoryLink
  /** the lane indices */
  from: number
  to: number
  x: number
  y1: number
  y2: number
}

export type Section = {
  key: string
  label: string
  x: number
  width: number
  months: { key: string; label: string; x: number; width: number }[]
}

export type PlacedLane = { lane: HistoryLane; index: number; top: number; middle: number }

export type Layout = {
  width: number
  height: number
  /** the height of the axis (years, and months where any year is dense) */
  headerHeight: number
  hasMonths: boolean
  lanes: PlacedLane[]
  sections: Section[]
  events: PlacedEvent[]
  links: PlacedLink[]
  more: number
}

type Column = { key: string; width: number; x: number }

function sorted(events: HistoryEvent[] | undefined): HistoryEvent[] {
  return [...(events ?? [])].sort((a, b) => {
    const da = dayKey(a.at)
    const db = dayKey(b.at)
    if (da !== db) return da < db ? -1 : 1
    return (KIND_ORDER[a.kind] ?? 9) - (KIND_ORDER[b.kind] ?? 9)
  })
}

/** `minWidth`: the width of the page's frame, so that the bands reach its edge. */
export function layoutSwimlane(history: HistoryResponse, minWidth = 320): Layout {
  const g = GEOMETRY
  const lanes = history.lanes
  const ordered = lanes.map((lane) => sorted(lane.visible ? lane.events : []))

  // where a link falls: on the child's first version when it is there
  const linkKey = (link: HistoryLink): string => {
    const index = lanes.findIndex((lane) => lane.id === link.to)
    const version = link.version_id && index >= 0
      ? ordered[index].find((event) => event.id === link.version_id)
      : undefined
    return dayKey(version ? version.at : link.at)
  }

  // columns: one per day that holds an event or a link, undated first
  const keys = new Set<string>()
  ordered.forEach((events) => events.forEach((event) => keys.add(dayKey(event.at))))
  history.links.forEach((link) => keys.add(linkKey(link)))
  const days = [...keys].sort((a, b) => (a === b ? 0 : a === '' ? -1 : b === '' ? 1 : a < b ? -1 : 1))
  const widest = new Map<string, number>()
  ordered.forEach((events) => {
    const per = new Map<string, number>()
    events.forEach((event) => per.set(dayKey(event.at), (per.get(dayKey(event.at)) ?? 0) + 1))
    per.forEach((count, key) => widest.set(key, Math.max(widest.get(key) ?? 0, count)))
  })
  let cursor = g.margin
  const columns = new Map<string, Column>()
  for (const key of days) {
    const width = g.colPad + Math.max(1, widest.get(key) ?? 1) * g.eventWidth
    columns.set(key, { key, width, x: cursor })
    cursor += width
  }
  const width = Math.max(cursor + g.margin, minWidth)

  // sections by year; months where a year has many days
  const sections: Section[] = []
  for (const column of columns.values()) {
    const year = column.key ? column.key.slice(0, 4) : ''
    let section = sections[sections.length - 1]
    if (!section || section.key !== (year || 'undated')) {
      section = { key: year || 'undated', label: year || 'Undated', x: column.x, width: 0, months: [] }
      sections.push(section)
    }
    section.width = column.x + column.width - section.x
  }
  let hasMonths = false
  for (const section of sections) {
    if (section.key === 'undated') continue
    const inYear = [...columns.values()].filter((c) => c.key.startsWith(section.key))
    if (inYear.length <= DENSE_COLUMNS) continue
    hasMonths = true
    for (const column of inYear) {
      const month = column.key.slice(0, 7)
      const last = section.months[section.months.length - 1]
      if (last && last.key === month) {
        last.width = column.x + column.width - last.x
      } else {
        section.months.push({
          key: month, label: MONTHS[Number(month.slice(5, 7)) - 1] ?? month.slice(5), x: column.x, width: column.width,
        })
      }
    }
  }
  const headerHeight = g.sectionHeight + (hasMonths ? g.monthHeight : 0)

  // events and links
  const placedLanes: PlacedLane[] = lanes.map((lane, index) => ({
    lane, index, top: headerHeight + index * g.rowHeight, middle: headerHeight + index * g.rowHeight + g.rowHeight / 2,
  }))
  const events: PlacedEvent[] = []
  ordered.forEach((list, laneIndex) => {
    const used = new Map<string, number>()
    list.forEach((event, i) => {
      const key = dayKey(event.at)
      const column = columns.get(key) as Column
      const sub = used.get(key) ?? 0
      used.set(key, sub + 1)
      events.push({
        key: `${lanes[laneIndex].id}:${event.kind}:${event.id ?? event.day ?? key}:${event.method ?? ''}:${i}`,
        lane: laneIndex,
        laneId: lanes[laneIndex].id,
        event,
        x: column.x + g.colPad / 2 + sub * g.eventWidth + g.eventWidth / 2,
        y: placedLanes[laneIndex].middle,
      })
    })
  })
  const links: PlacedLink[] = []
  history.links.forEach((link, i) => {
    const from = lanes.findIndex((lane) => lane.id === link.from)
    const to = lanes.findIndex((lane) => lane.id === link.to)
    if (from < 0 || to < 0) return
    const version = link.version_id
      ? events.find((e) => e.lane === to && e.event.id === link.version_id)
      : undefined
    const column = columns.get(linkKey(link)) as Column
    links.push({
      key: `${link.kind}:${link.from}:${link.to}:${i}`,
      link, from, to,
      x: version ? version.x : column.x + column.width / 2,
      y1: placedLanes[from].middle,
      y2: placedLanes[to].middle,
    })
  })

  return {
    width,
    height: headerHeight + lanes.length * g.rowHeight + (history.more > 0 ? g.footer : 0),
    headerHeight,
    hasMonths,
    lanes: placedLanes,
    sections,
    events,
    links,
    more: history.more,
  }
}

/** The lane's label: its number and name; a stub says why it is empty. */
export function laneTitle(lane: HistoryLane): string {
  if (!lane.visible) return lane.withdrawn ? `#${lane.catalog_number ?? '?'} withdrawn` : (lane.label ?? 'not visible')
  const number = lane.catalog_number != null ? `#${lane.catalog_number}` : ''
  return [number, lane.name ?? ''].filter(Boolean).join(' ') || lane.id.slice(0, 8)
}
