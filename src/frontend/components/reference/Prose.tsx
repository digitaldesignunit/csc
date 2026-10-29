import { isMarked, type Para, type Run } from '@/lib/dataModelText'

/** Marks of the sentences read loosely from the specification show in development only. */
const SHOW_MARKS = process.env.NODE_ENV === 'development'

function RunView({ run }: { run: Run }) {
  if (!isMarked(run)) return <>{run}</>
  if (!SHOW_MARKS) return <>{run.text}</>
  return (
    <>
      <mark
        className="rounded bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-500/30"
        title={`Spec ${run.spec}: ${run.note}`}
        data-spec={run.spec}
      >
        {run.text}
      </mark>
      <sup className="ml-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">[spec {run.spec}]</sup>
    </>
  )
}

/** The runs of a paragraph, as inline text. */
export function Runs({ runs }: { runs: Para | string }) {
  const list: Para = typeof runs === 'string' ? [runs] : runs
  return (
    <>
      {list.map((run, index) => (
        <RunView key={index} run={run} />
      ))}
    </>
  )
}

/** A paragraph. */
export function Prose({ runs, className }: { runs: Para | string; className?: string }) {
  return (
    <p className={className}>
      <Runs runs={runs} />
    </p>
  )
}
