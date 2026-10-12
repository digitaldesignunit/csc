'use client'

/**
 * The frame of the evidence form (decision 8.134 a): numbered sections that
 * differ visibly (heading band, icon, a coloured edge by state), an outline
 * beside the form on a desktop and a progress line on a phone. Each shows
 * done / missing / error / optional and jumps to its section.
 */
import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  Check,
  ChevronDown,
  CircleDashed,
  ClipboardCheck,
  ListChecks,
  Paperclip,
  Ruler,
  StickyNote,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { SectionId, SectionState } from '@/lib/evidence/issues'
import { cn } from '@/lib/utils'

export type FormStepId = SectionId | 'check'

export const STEP_ICONS: Record<FormStepId, LucideIcon> = {
  method: ListChecks,
  who: CalendarClock,
  what: Ruler,
  files: Paperclip,
  notes: StickyNote,
  check: ClipboardCheck,
}

export type Step = {
  id: FormStepId
  title: string
  state: SectionState | 'check'
  /** problems or missing fields of the section */
  count: number
}

const EDGE: Record<SectionState | 'check', string> = {
  done: 'border-l-emerald-500',
  missing: 'border-l-amber-500',
  error: 'border-l-destructive',
  optional: 'border-l-border',
  check: 'border-l-primary',
}

const STATE_WORDS: Record<SectionState | 'check', string> = {
  done: 'Done',
  missing: 'To do',
  error: 'Check',
  optional: 'Optional',
  check: '',
}

function StateMark({ state, className }: { state: SectionState | 'check'; className?: string }) {
  if (state === 'done') return <Check className={cn('h-4 w-4 text-emerald-600 dark:text-emerald-400', className)} aria-hidden />
  if (state === 'error') return <AlertTriangle className={cn('h-4 w-4 text-destructive', className)} aria-hidden />
  if (state === 'missing') return <CircleDashed className={cn('h-4 w-4 text-amber-600 dark:text-amber-400', className)} aria-hidden />
  if (state === 'check') return <ClipboardCheck className={cn('h-4 w-4 text-primary', className)} aria-hidden />
  return <CircleDashed className={cn('h-4 w-4 text-muted-foreground', className)} aria-hidden />
}

/** The DOM id of a section. */
export const sectionDomId = (id: FormStepId) => `sec-${id}`

export function jumpToSection(id: FormStepId) {
  const element = document.getElementById(sectionDomId(id))
  if (!element) return
  element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  element.focus({ preventScroll: true })
}

export function FormSection({
  id,
  number,
  title,
  state,
  count,
  actions,
  summary,
  children,
  className,
}: {
  id: FormStepId
  number: number
  title: string
  state: SectionState | 'check'
  count?: number
  /** a short line beside the heading (a chosen method, a count) */
  summary?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  const Icon = STEP_ICONS[id]
  return (
    <section
      id={sectionDomId(id)}
      tabIndex={-1}
      aria-labelledby={`${sectionDomId(id)}-title`}
      className={cn(
        'scroll-mt-28 overflow-hidden rounded-xl border border-l-4 bg-card shadow-sm outline-none lg:scroll-mt-6',
        EDGE[state],
        className,
      )}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border bg-muted/40 px-4 py-2.5">
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
          aria-hidden
        >
          {number}
        </span>
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <h2 id={`${sectionDomId(id)}-title`} className="text-base font-semibold">{title}</h2>
        {state !== 'check' && (
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
              state === 'error' && 'border-destructive/40 text-destructive',
              state === 'missing' && 'border-amber-500/50 text-amber-700 dark:text-amber-300',
              state === 'done' && 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300',
              state === 'optional' && 'border-border text-muted-foreground',
            )}
          >
            <StateMark state={state} className="h-3 w-3" />
            {STATE_WORDS[state]}{(state === 'missing' || state === 'error') && count ? ` (${count})` : ''}
          </span>
        )}
        {summary && <span className="min-w-0 text-xs text-muted-foreground">{summary}</span>}
        {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
      <div className="space-y-4 p-4">{children}</div>
    </section>
  )
}

/** Which section is in view: the last one whose top has passed the upper part of the screen. */
export function useActiveStep(ids: FormStepId[]): FormStepId {
  const [active, setActive] = useState<FormStepId>(ids[0])
  const key = ids.join(',')
  useEffect(() => {
    const list = key.split(',') as FormStepId[]
    const onScroll = () => {
      let current = list[0]
      for (const id of list) {
        const element = document.getElementById(sectionDomId(id))
        if (element && element.getBoundingClientRect().top < window.innerHeight * 0.35) current = id
      }
      setActive(current)
    }
    onScroll()
    // the page scrolls inside a container of the app shell as well as the window
    window.addEventListener('scroll', onScroll, { passive: true, capture: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onScroll)
    }
  }, [key])
  return active
}

export function Outline({ steps, active }: { steps: Step[]; active: FormStepId }) {
  return (
    <nav aria-label="Sections of the form" className="hidden lg:block">
      <ol className="sticky top-6 space-y-1">
        {steps.map((step, index) => {
          const Icon = STEP_ICONS[step.id]
          return (
            <li key={step.id}>
              <button
                type="button"
                onClick={() => jumpToSection(step.id)}
                aria-current={active === step.id ? 'step' : undefined}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md border border-transparent px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted/60',
                  active === step.id && 'border-border bg-muted font-medium',
                )}
              >
                <StateMark state={step.state} />
                <span className="text-muted-foreground tabular-nums">{index + 1}.</span>
                <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{step.title}</span>
                {(step.state === 'missing' || step.state === 'error') && step.count > 0 && (
                  <span
                    className={cn(
                      'rounded-full px-1.5 text-[11px] font-medium tabular-nums',
                      step.state === 'error' ? 'bg-destructive/15 text-destructive' : 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
                    )}
                    aria-label={`${step.count} to look at`}
                  >
                    {step.count}
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

const BAR: Record<SectionState | 'check', string> = {
  done: 'bg-emerald-500',
  missing: 'bg-amber-500',
  error: 'bg-destructive',
  optional: 'bg-muted-foreground/30',
  check: 'bg-primary',
}

/** The phone's outline: where you are among the sections, one tap to another. */
export function ProgressLine({ steps, active }: { steps: Step[]; active: FormStepId }) {
  const index = Math.max(0, steps.findIndex((s) => s.id === active))
  const current = steps[index]
  return (
    <div
      className="sticky top-0 z-20 -mx-4 border-b border-border bg-background/95 px-4 py-2 backdrop-blur lg:hidden"
      role="navigation"
      aria-label="Progress through the form"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm">
          <span className="text-muted-foreground">Step {index + 1} of {steps.length}: </span>
          <span className="font-medium">{current.title}</span>
        </p>
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" variant="ghost" size="sm" className="h-7 shrink-0 gap-1 px-2 text-xs">
              Sections<ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64 p-1">
            <ul>
              {steps.map((step, i) => (
                <li key={step.id}>
                  <button
                    type="button"
                    onClick={() => jumpToSection(step.id)}
                    className="flex w-full items-center gap-2 rounded px-2 py-2 text-left text-sm hover:bg-muted"
                  >
                    <StateMark state={step.state} />
                    <span className="tabular-nums text-muted-foreground">{i + 1}.</span>
                    <span className="min-w-0 flex-1 truncate">{step.title}</span>
                    {(step.state === 'missing' || step.state === 'error') && step.count > 0 && (
                      <span className="text-xs tabular-nums text-muted-foreground">{step.count}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      </div>
      <div className="mt-1.5 flex gap-1" aria-hidden>
        {steps.map((step) => (
          <button
            key={step.id}
            type="button"
            tabIndex={-1}
            onClick={() => jumpToSection(step.id)}
            className={cn('h-1.5 flex-1 rounded-full', BAR[step.state], step.id === active ? 'h-2' : 'opacity-70')}
          />
        ))}
      </div>
    </div>
  )
}

/** A block inside a section that folds to one line (shared settings, defaults). */
export function FoldCard({
  title,
  summary,
  open,
  onOpenChange,
  state,
  children,
}: {
  title: string
  summary?: React.ReactNode
  open: boolean
  onOpenChange: (open: boolean) => void
  state?: SectionState
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-border bg-background">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', !open && '-rotate-90')} aria-hidden />
        <span className="text-sm font-medium">{title}</span>
        {state && state !== 'optional' && <StateMark state={state} className="h-3.5 w-3.5" />}
        {!open && summary && <span className="min-w-0 truncate text-xs text-muted-foreground">{summary}</span>}
      </button>
      {open && <div className="space-y-3 border-t border-border p-3">{children}</div>}
    </div>
  )
}
