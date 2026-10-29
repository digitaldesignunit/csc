import { Network } from 'lucide-react'

import DataTable, { type Column } from '@/components/reference/DataTable'
import ModelDiagram from '@/components/reference/ModelDiagram'
import ReferenceTabs, { FoldList } from '@/components/reference/ReferenceTabs'
import { Prose, Runs } from '@/components/reference/Prose'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  EXAMPLE_DATASET,
  EXAMPLE_EVIDENCE,
  EXAMPLE_ID_NOTE,
  EXAMPLE_IDENTITY,
  EXAMPLE_PIECE_INTRO,
  EXAMPLE_SNAPSHOT_V0,
  EXAMPLE_SNAPSHOT_V1,
  type ExampleRecord,
} from '@/lib/dataModelExamples'
import { exampleRows, rawJson, type ExampleRow } from '@/lib/dataModelRows'
import {
  ENTITY_SECTIONS,
  EXAMPLE_SECTION_ID,
  METHOD_TIER,
  OVERVIEW,
  PAGE_LEAD,
  PAGE_TITLE,
  QUANTITY_FACTS,
  RULES,
  RULES_INTRO,
  RULES_TITLE,
  VOCABULARIES_INTRO,
  VOCAB_SECTIONS,
  type FieldRow,
  type FieldTable,
  type Section,
  type VocabSection,
} from '@/lib/dataModelText'
import { vocabEntries, type VocabEntry } from '@/lib/dataModelVocab'
import { TAB_SECTIONS, type TabId } from '@/lib/dataModelTabs'
import type { EvidenceMethod, Quantity } from '@/generated/Vocab'

export const metadata = { title: PAGE_TITLE }

const CODE = 'rounded bg-muted px-1 py-0.5 font-mono text-xs'

function Heading({ id, children, level = 2 }: { id: string; children: React.ReactNode; level?: 2 | 3 }) {
  const Tag = level === 2 ? 'h2' : 'h3'
  return (
    <Tag id={id} className={level === 2 ? 'scroll-mt-20 text-base font-semibold' : 'scroll-mt-20 text-sm font-semibold'}>
      <a href={`#${id}`} className="hover:underline">{children}</a>
    </Tag>
  )
}

function Block({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <Card id={id} className="scroll-mt-20 bg-card/75">
      <CardHeader>
        <CardTitle className="text-base">
          <a href={`#${id}`} className="hover:underline">{title}</a>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 text-sm leading-relaxed">{children}</CardContent>
    </Card>
  )
}

// FIELD TABLES -------------------------------------------------------------------
const FIELD_COLUMNS: Column<FieldRow>[] = [
  { key: 'name', header: 'Field', render: (r) => <code className={CODE}>{r.name}</code>, className: 'whitespace-nowrap' },
  { key: 'meaning', header: 'Meaning', render: (r) => <Runs runs={r.meaning} />, className: 'min-w-56' },
  { key: 'type', header: 'Type', render: (r) => r.type },
  { key: 'example', header: 'Example', render: (r) => r.example || '-' },
  {
    key: 'derived',
    header: 'Set by',
    render: (r) => (r.derived ? 'the server' : 'a person'),
    className: 'whitespace-nowrap',
  },
]

function FieldTableView({ table }: { table: FieldTable }) {
  return (
    <div className="space-y-2">
      <Heading id={table.id} level={3}>{table.title}</Heading>
      {table.intro && <Prose runs={table.intro} />}
      <DataTable columns={FIELD_COLUMNS} rows={table.rows} label={table.title} rowKey={(r) => r.name} />
    </div>
  )
}

function SectionView({ section }: { section: Section }) {
  return (
    <Block id={section.id} title={section.title}>
      {section.lead.map((para, i) => <Prose key={i} runs={para} />)}
      {section.tables?.map((table) => <FieldTableView key={table.id} table={table} />)}
      {section.after?.map((para, i) => <Prose key={`after-${i}`} runs={para} />)}
    </Block>
  )
}

// VOCABULARIES -------------------------------------------------------------------
function extraColumns(vocab: VocabSection['vocab']): Column<VocabEntry>[] {
  if (vocab === 'quantity') {
    return [
      { key: 'unit', header: 'Unit', render: (e) => QUANTITY_FACTS[e.value as Quantity]?.unit ?? '' },
      { key: 'kind', header: 'Kind', render: (e) => QUANTITY_FACTS[e.value as Quantity]?.kind ?? '' },
      { key: 'scope', header: 'Scope', render: (e) => QUANTITY_FACTS[e.value as Quantity]?.scope ?? '' },
    ]
  }
  if (vocab === 'evidence_method') {
    return [{ key: 'tier', header: 'Source tier', render: (e) => METHOD_TIER[e.value as EvidenceMethod] ?? '' }]
  }
  return []
}

function VocabBody({ section }: { section: VocabSection }) {
  const columns: Column<VocabEntry>[] = [
    { key: 'label', header: 'Label', render: (e) => <span className="font-medium">{e.label}</span> },
    {
      key: 'value',
      header: section.valueHeader,
      render: (e) => <code className={CODE}>{e.value}</code>,
      className: 'whitespace-nowrap',
    },
    { key: 'meaning', header: 'Meaning', render: (e) => e.description, className: 'min-w-56' },
    ...extraColumns(section.vocab),
  ]
  return (
    <>
      <Prose runs={section.intro} />
      <DataTable columns={columns} rows={vocabEntries(section.vocab)} label={section.title} rowKey={(e) => e.value} />
    </>
  )
}

// EXAMPLES -----------------------------------------------------------------------
const EXAMPLE_COLUMNS: Column<ExampleRow>[] = [
  {
    key: 'field',
    header: 'Field',
    render: (r) => <code className={r.nested ? `${CODE} ml-3` : CODE}>{r.field}</code>,
    className: 'whitespace-nowrap',
  },
  { key: 'value', header: 'Value', render: (r) => <span className="break-words font-mono text-xs">{r.value}</span>, className: 'max-w-64' },
  { key: 'comment', header: 'Comment', render: (r) => <Runs runs={r.comment} />, className: 'min-w-56' },
]

function ExampleBody({ record }: { record: ExampleRecord }) {
  return (
    <>
      <Prose runs={record.intro} />
      <DataTable columns={EXAMPLE_COLUMNS} rows={exampleRows(record)} label={record.title} rowKey={(r) => r.field} />
      <details className="rounded-md border border-border bg-muted/40 text-xs">
        <summary className="cursor-pointer px-3 py-1.5 font-medium">Raw JSON of this record</summary>
        <pre className="overflow-x-auto px-3 pb-3 font-mono leading-snug">{rawJson(record)}</pre>
      </details>
    </>
  )
}

// THE PAGE -----------------------------------------------------------------------
const sectionsOf = (tab: keyof typeof TAB_SECTIONS) =>
  (TAB_SECTIONS[tab] ?? []).map((id) => ENTITY_SECTIONS.find((section) => section.id === id) as Section)

export default function ReferencePage() {
  const panels: Record<TabId, React.ReactNode> = {
    overview: (
      <>
        <Block id={OVERVIEW.id} title={OVERVIEW.title}>
          {OVERVIEW.lead.map((para, i) => <Prose key={i} runs={para} />)}
          <ModelDiagram />
        </Block>
        <Block id="rules" title={RULES_TITLE}>
          <Prose runs={RULES_INTRO} />
          <ol className="space-y-4">
            {RULES.map((rule, index) => (
              <li key={rule.id} id={rule.id} className="scroll-mt-20 space-y-1 border-l-2 border-primary/40 pl-4">
                <p className="font-medium">{index + 1}. {rule.title}</p>
                <Prose runs={rule.body} className="text-muted-foreground" />
              </li>
            ))}
          </ol>
        </Block>
      </>
    ),
    dataset: <>{sectionsOf('dataset').map((section) => <SectionView key={section.id} section={section} />)}</>,
    identity: <>{sectionsOf('identity').map((section) => <SectionView key={section.id} section={section} />)}</>,
    snapshot: <>{sectionsOf('snapshot').map((section) => <SectionView key={section.id} section={section} />)}</>,
    evidence: <>{sectionsOf('evidence').map((section) => <SectionView key={section.id} section={section} />)}</>,
    vocabularies: (
      <Block id="vocabularies" title="Lists of values">
        <Prose runs={VOCABULARIES_INTRO} />
        <FoldList
          group="lists"
          items={VOCAB_SECTIONS.map((section) => ({ id: section.id, title: section.title, content: <VocabBody section={section} /> }))}
        />
      </Block>
    ),
    example: (
      <Block id={EXAMPLE_SECTION_ID} title="An example element">
        <Prose runs={EXAMPLE_PIECE_INTRO} />
        <p className="text-xs text-muted-foreground">{EXAMPLE_ID_NOTE}</p>
        <FoldList
          group="example"
          items={[EXAMPLE_DATASET, EXAMPLE_IDENTITY, EXAMPLE_SNAPSHOT_V0, EXAMPLE_SNAPSHOT_V1, ...EXAMPLE_EVIDENCE].map((record) => ({
            id: record.id,
            title: record.title,
            content: <ExampleBody record={record} />,
          }))}
        />
      </Block>
    ),
  }
  return (
    <div className="relative min-h-full">
      <div className="container mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
        <div className="mb-4 sm:mb-6">
          <div className="mb-2 flex items-center gap-2 sm:gap-3">
            <Network className="h-6 w-6 text-primary" aria-hidden />
            <h1 className="text-xl font-bold sm:text-2xl">{PAGE_TITLE}</h1>
          </div>
          <p className="text-sm text-muted-foreground sm:text-base"><Runs runs={PAGE_LEAD} /></p>
        </div>

        <div className="relative z-10">
          <ReferenceTabs panels={panels} />
        </div>
      </div>
    </div>
  )
}
