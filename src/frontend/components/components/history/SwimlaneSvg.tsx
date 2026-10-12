'use client'

/**
 * The drawing of the swimlane graph (decision 8.140 f): one SVG, no library.
 * The same component draws the page (palette `screen`, theme colours) and the
 * export (palette `print`, fixed colours, the lane names inside, a legend), so
 * the image is the page's graph with every group opened.
 */
import type { Ref } from 'react'

import {
  GEOMETRY,
  describeEvent,
  glyphOf,
  laneTitle,
  type Layout,
  type PlacedEvent,
} from '@/lib/history/swimlane'

export type Palette = 'screen' | 'print'

type Colours = {
  ink: string
  muted: string
  line: string
  band: string
  rootBand: string
  card: string
  origin: string
  version: string
  evidence: string
  exit: string
  withdrawal: string
  link: string
}

const COLOURS: Record<Palette, Colours> = {
  screen: {
    ink: 'var(--foreground)',
    muted: 'var(--muted-foreground)',
    line: 'var(--border)',
    band: 'var(--muted)',
    rootBand: 'var(--primary)',
    card: 'var(--card)',
    origin: '#0d9488',
    version: 'var(--primary)',
    evidence: '#d97706',
    exit: '#e11d48',
    withdrawal: '#78716c',
    link: 'var(--muted-foreground)',
  },
  print: {
    ink: '#111111',
    muted: '#555555',
    line: '#c8c8c8',
    band: '#f3f3f3',
    rootBand: '#dbeafe',
    card: '#ffffff',
    origin: '#0f766e',
    version: '#1d4ed8',
    evidence: '#b45309',
    exit: '#be123c',
    withdrawal: '#57534e',
    link: '#444444',
  },
}

export const LABEL_WIDTH = 190
const LEGEND_HEIGHT = 74
const TITLE_HEIGHT = 30
const FONT = 'Helvetica, Arial, sans-serif'

function GlyphShape({
  event, x, y, colours, active,
}: {
  event: PlacedEvent['event']
  x: number
  y: number
  colours: Colours
  active?: boolean
}) {
  const glyph = glyphOf(event)
  switch (glyph) {
    case 'origin':
      return <circle cx={x} cy={y} r={6} fill={colours.card} stroke={colours.origin} strokeWidth={2.5} />
    case 'version':
    case 'version-corrected':
      return (
        <>
          {active && <circle cx={x} cy={y} r={11} fill="none" stroke={colours.version} strokeWidth={1.5} />}
          <circle
            cx={x} cy={y} r={7}
            fill={glyph === 'version' ? colours.version : colours.card}
            stroke={colours.version} strokeWidth={2}
            strokeDasharray={glyph === 'version' ? undefined : '3 2'}
          />
        </>
      )
    case 'group':
      return (
        <>
          <rect x={x - 11} y={y - 8} width={22} height={16} rx={4} fill={colours.evidence} />
          <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fontWeight={700} fill="#ffffff" fontFamily={FONT}>
            {event.count ?? event.ids?.length ?? ''}
          </text>
        </>
      )
    case 'record':
      return <rect x={x - 5} y={y - 5} width={10} height={10} rx={2} fill={colours.evidence} />
    case 'exit':
      return <rect x={x - 3.5} y={y - 10} width={7} height={20} rx={2} fill={colours.exit} />
    default:
      return <path d={`M ${x - 7} ${y - 6} L ${x + 7} ${y - 6} L ${x} ${y + 7} Z`} fill={colours.withdrawal} />
  }
}

function LegendRow({ colours, x, y }: { colours: Colours; x: number; y: number }) {
  const item = (dx: number, label: string, shape: React.ReactNode) => (
    <g key={label} transform={`translate(${x + dx}, ${y})`}>
      {shape}
      <text x={16} y={4} fontSize={11} fill={colours.ink} fontFamily={FONT}>{label}</text>
    </g>
  )
  return (
    <>
      {item(0, 'Start of the piece', <circle cx={0} cy={0} r={6} fill={colours.card} stroke={colours.origin} strokeWidth={2.5} />)}
      {item(150, 'Version', <circle cx={0} cy={0} r={7} fill={colours.version} stroke={colours.version} strokeWidth={2} />)}
      {item(240, 'Replaced by a correction', <circle cx={0} cy={0} r={7} fill={colours.card} stroke={colours.version} strokeWidth={2} strokeDasharray="3 2" />)}
      {item(420, 'Evidence record', <rect x={-5} y={-5} width={10} height={10} rx={2} fill={colours.evidence} />)}
      {item(560, 'Left circulation', <rect x={-3.5} y={-10} width={7} height={20} rx={2} fill={colours.exit} />)}
      {item(690, 'Withdrawn', <path d="M -7 -6 L 7 -6 L 0 7 Z" fill={colours.withdrawal} />)}
    </>
  )
}

export default function SwimlaneSvg({
  layout,
  palette = 'screen',
  withLabels = false,
  title,
  legend = false,
  activeVersionId,
  focusKey,
  onEvent,
  onCollapse,
  onHover,
  svgRef,
}: {
  layout: Layout
  palette?: Palette
  /** the lane names inside the image (the export); the page has its own column */
  withLabels?: boolean
  title?: string
  legend?: boolean
  activeVersionId?: string
  focusKey?: string | null
  onEvent?: (placed: PlacedEvent) => void
  /** close an opened evidence group (a click on its bracket) */
  onCollapse?: (groupKey: string) => void
  onHover?: (placed: PlacedEvent | null, target: Element | null) => void
  svgRef?: Ref<SVGSVGElement>
}) {
  const colours = COLOURS[palette]
  const g = GEOMETRY
  const left = withLabels ? LABEL_WIDTH : 0
  const top = title ? TITLE_HEIGHT : 0
  const foot = legend ? LEGEND_HEIGHT : 0
  const width = left + layout.width
  const height = top + layout.height + foot
  const interactive = Boolean(onEvent)

  return (
    <svg
      ref={svgRef}
      xmlns="http://www.w3.org/2000/svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role={interactive ? 'group' : 'img'}
      aria-label={title ?? 'History of the piece and its relatives'}
      fontFamily={FONT}
    >
      {palette === 'print' && <rect x={0} y={0} width={width} height={height} fill="#ffffff" />}
      {title && (
        <text x={g.margin} y={20} fontSize={14} fontWeight={700} fill={colours.ink}>{title}</text>
      )}
      <g transform={`translate(${left}, ${top})`}>
        {/* lane bands */}
        {layout.lanes.map(({ lane, index, top: y }) => (
          <g key={lane.id}>
            <rect
              x={0} y={y} width={layout.width} height={g.rowHeight}
              fill={lane.role === 'piece' ? colours.rootBand : index % 2 ? 'transparent' : colours.band}
              opacity={lane.role === 'piece' ? 0.13 : 0.55}
            />
            <line x1={0} x2={layout.width} y1={y + g.rowHeight} y2={y + g.rowHeight} stroke={colours.line} strokeWidth={0.75} />
          </g>
        ))}

        {/* time axis */}
        {layout.sections.map((section) => (
          <g key={section.key}>
            <line x1={section.x} x2={section.x} y1={0} y2={layout.height - (layout.more ? g.footer : 0)} stroke={colours.line} strokeWidth={0.75} />
            <text x={section.x + 6} y={15} fontSize={12} fontWeight={700} fill={colours.ink}>{section.label}</text>
            {section.months.map((month) => (
              <g key={month.key}>
                <line x1={month.x} x2={month.x} y1={g.sectionHeight} y2={layout.headerHeight} stroke={colours.line} strokeWidth={0.5} />
                <text x={month.x + 4} y={g.sectionHeight + 13} fontSize={10} fill={colours.muted}>{month.label}</text>
              </g>
            ))}
          </g>
        ))}
        <line x1={0} x2={layout.width} y1={layout.headerHeight} y2={layout.headerHeight} stroke={colours.line} strokeWidth={0.75} />

        {/* the lane lines: from the first to the last event of a lane */}
        {layout.lanes.map(({ lane, index, middle }) => {
          const xs = layout.events.filter((e) => e.lane === index).map((e) => e.x)
          if (xs.length < 2) return null
          return (
            <line key={lane.id} x1={Math.min(...xs)} x2={Math.max(...xs)} y1={middle} y2={middle}
              stroke={colours.muted} strokeWidth={1.5} opacity={0.6} />
          )
        })}

        {/* links between lanes */}
        {layout.links.map((placed) => {
          const same = layout.links.filter((l) => l.link.to === placed.link.to)
          const dx = (same.indexOf(placed) - (same.length - 1) / 2) * 7
          const down = placed.y2 > placed.y1
          const x = placed.x + dx
          const start = placed.y1 + (down ? 10 : -10)
          const end = placed.y2 + (down ? -11 : 11)
          const mid = (start + end) / 2
          return (
            <g key={placed.key} aria-hidden>
              <path d={`M ${x} ${start} C ${x} ${mid}, ${x} ${mid}, ${x} ${end}`} fill="none"
                stroke={colours.link} strokeWidth={1.6} strokeDasharray="5 3" />
              <path d={down ? `M ${x - 4} ${end - 6} L ${x + 4} ${end - 6} L ${x} ${end} Z` : `M ${x - 4} ${end + 6} L ${x + 4} ${end + 6} L ${x} ${end} Z`}
                fill={colours.link} />
              <text x={x + 6} y={mid + 3} fontSize={10} fill={colours.muted}
                stroke={colours.card} strokeWidth={3} paintOrder="stroke" fontFamily={FONT}>
                {placed.link.kind === 'cut' ? 'cut' : 'assembled'}
              </text>
            </g>
          )
        })}

        {/* stubs and empty lanes say so */}
        {layout.lanes.map(({ lane, middle }) => (
          !lane.visible ? (
            <text key={`stub-${lane.id}`} x={g.margin} y={middle + 4} fontSize={11} fill={colours.muted} fontStyle="italic">
              {laneTitle(lane)}
            </text>
          ) : null
        ))}

        {/* the records of an opened group sit in a bracket; a click on it closes the group */}
        {[...new Set(layout.events.map((e) => e.event.groupKey).filter(Boolean) as string[])].map((key) => {
          const members = layout.events.filter((e) => e.event.groupKey === key)
          const x1 = Math.min(...members.map((m) => m.x)) - 17
          const x2 = Math.max(...members.map((m) => m.x)) + 17
          const y = members[0].y
          return (
            <rect key={`bracket-${key}`} x={x1} y={y - 17} width={x2 - x1} height={34} rx={9}
              fill={colours.evidence} fillOpacity={0.1} stroke={colours.evidence} strokeWidth={1} strokeDasharray="3 2"
              style={onCollapse ? { cursor: 'pointer' } : undefined}
              onClick={onCollapse ? () => onCollapse(key) : undefined}>
              <title>Click to close the group</title>
            </rect>
          )
        })}

        {/* events */}
        {layout.events.map((placed) => {
          const { event } = placed
          const described = describeEvent(event)
          const lane = layout.lanes[placed.lane].lane
          const active = Boolean(activeVersionId) && event.kind === 'version' && event.id === activeVersionId
          return (
            <g
              key={placed.key}
              role={interactive ? 'button' : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-label={interactive ? `${laneTitle(lane)}: ${described.title}, ${described.lines.find((l) => /\d{4}|unknown/.test(l)) ?? ''}` : undefined}
              style={interactive ? { cursor: 'pointer', outline: 'none' } : undefined}
              onClick={interactive ? () => onEvent?.(placed) : undefined}
              onKeyDown={interactive ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEvent?.(placed) }
              } : undefined}
              onMouseEnter={interactive ? (e) => onHover?.(placed, e.currentTarget) : undefined}
              onMouseLeave={interactive ? () => onHover?.(null, null) : undefined}
              onFocus={interactive ? (e) => onHover?.(placed, e.currentTarget) : undefined}
              onBlur={interactive ? () => onHover?.(null, null) : undefined}
            >
              {interactive && <circle cx={placed.x} cy={placed.y} r={15} fill="transparent" />}
              {focusKey === placed.key && (
                <circle cx={placed.x} cy={placed.y} r={14} fill="none" stroke={colours.ink} strokeWidth={1.5} />
              )}
              <GlyphShape event={event} x={placed.x} y={placed.y} colours={colours} active={active} />
              {described.short && event.kind !== 'evidence_group' && (
                <text x={placed.x} y={placed.y + 23} textAnchor="middle" fontSize={9} fill={colours.muted}>
                  {described.short}
                </text>
              )}
            </g>
          )
        })}

        {layout.more > 0 && (
          <text x={g.margin} y={layout.height - 8} fontSize={11} fill={colours.muted}>
            {`+${layout.more} more ${layout.more === 1 ? 'piece' : 'pieces'} not shown`}
          </text>
        )}
      </g>

      {/* the lane names, inside the image only for the export */}
      {withLabels && layout.lanes.map(({ lane, middle }) => (
        <g key={`label-${lane.id}`} transform={`translate(0, ${top + middle})`}>
          <text x={g.margin} y={-3} fontSize={11} fontWeight={lane.role === 'piece' ? 700 : 400} fill={colours.ink}>
            {truncate(laneTitle(lane), 28)}
          </text>
          <text x={g.margin} y={11} fontSize={9} fill={colours.muted}>
            {lane.visible ? (lane.dataset ?? '') : ''}
          </text>
        </g>
      ))}
      {withLabels && (
        <line x1={left} x2={left} y1={top} y2={top + layout.height} stroke={colours.line} strokeWidth={1} />
      )}

      {legend && (
        <g transform={`translate(0, ${top + layout.height + 14})`}>
          <text x={g.margin} y={0} fontSize={11} fontWeight={700} fill={colours.ink}>Legend</text>
          <LegendRow colours={colours} x={g.margin + 6} y={26} />
          <text x={g.margin} y={52} fontSize={10} fill={colours.muted}>
            Dashed lines join a piece and the pieces it was cut into or assembled from, at the child&apos;s first version.
            The time axis is in sections by year and not to scale.
          </text>
        </g>
      )}
    </svg>
  )
}

function truncate(text: string, length: number): string {
  return text.length > length ? `${text.slice(0, length - 1)}...` : text
}
