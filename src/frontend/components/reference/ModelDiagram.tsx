/**
 * The four records and how they belong together, drawn as boxes: a dataset
 * holds many identities, an identity has many snapshots and many evidence
 * records, and an evidence record can name the one snapshot it refers to.
 */
const BOX = 'fill-card stroke-border'

function Box({ x, y, w, h, title, line }: { x: number; y: number; w: number; h: number; title: string; line: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} className={BOX} strokeWidth={1.5} />
      <text x={x + w / 2} y={y + h / 2 - 4} textAnchor="middle" className="fill-foreground" fontSize={15} fontWeight={600}>
        {title}
      </text>
      <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" className="fill-muted-foreground" fontSize={12}>
        {line}
      </text>
    </g>
  )
}

function Label({ x, y, text, anchor = 'start' }: { x: number; y: number; text: string; anchor?: 'start' | 'middle' | 'end' }) {
  return (
    <text x={x} y={y} textAnchor={anchor} className="fill-muted-foreground" fontSize={11.5}>
      {text}
    </text>
  )
}

export default function ModelDiagram() {
  return (
    <figure className="space-y-2">
      <svg
        viewBox="0 0 560 310"
        className="h-auto w-full max-w-xl text-border"
        role="img"
        aria-label="A dataset holds many component identities. An identity has many snapshots and many evidence records. An evidence record can name one snapshot."
      >
        <Box x={170} y={8} w={220} h={52} title="Dataset" line="a project: members and roles" />
        <Box x={170} y={110} w={220} h={52} title="Component identity" line="one physical element" />
        <Box x={20} y={226} w={230} h={60} title="Snapshot" line="one state: shape and condition" />
        <Box x={310} y={226} w={230} h={60} title="Evidence" line="a test, a document, an inspection" />

        <g className="stroke-muted-foreground" strokeWidth={1.5} fill="none">
          <path d="M280 60 L280 110" />
          <path d="M240 162 L135 226" />
          <path d="M320 162 L425 226" />
          <path d="M310 258 L250 258" strokeDasharray="5 4" />
        </g>
        <Label x={288} y={90} text="holds many" />
        <Label x={150} y={186} text="has many" anchor="end" />
        <Label x={410} y={186} text="has many" />
        <Label x={280} y={304} text="Evidence can name the one snapshot it refers to" anchor="middle" />
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        The four records. Everything about an element hangs on its identity; the shape hangs on a snapshot.
      </figcaption>
    </figure>
  )
}
