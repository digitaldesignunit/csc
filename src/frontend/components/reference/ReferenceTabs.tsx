'use client'

/**
 * The tabs of the "Data Model" page and the folded sections inside two of them
 * (decision 8.181 c, amended). The tab is in the address (`/reference#evidence`);
 * a link to any anchor opens its tab and its folded section and scrolls to it;
 * back and forward move between tabs; an unknown or empty hash is the Overview.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DEFAULT_TAB,
  EXAMPLE_OPEN_BY_DEFAULT,
  TABS,
  parseHash,
  type FoldGroup,
  type TabId,
} from '@/lib/dataModelTabs'

type Folds = Record<FoldGroup, string[]>

type FoldState = {
  open: Folds
  setOpen: (group: FoldGroup, values: string[]) => void
}

const FoldContext = createContext<FoldState | null>(null)

const INITIAL_FOLDS: Folds = { lists: [], example: EXAMPLE_OPEN_BY_DEFAULT }

/**
 * Scrolls to an element that may not be in the document yet (a tab or a folded section opens
 * first). The layout shifts while a fold opens, so the scroll is made once more a little later.
 */
function scrollToAnchor(anchor: string) {
  let tries = 0
  const attempt = () => {
    const element = document.getElementById(anchor)
    if (element) {
      element.scrollIntoView({ block: 'start' })
      window.setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ block: 'start' }), 350)
    } else if (tries++ < 20) {
      window.setTimeout(attempt, 50)
    }
  }
  window.setTimeout(attempt, 60)
}

export default function ReferenceTabs({ panels }: { panels: Record<TabId, ReactNode> }) {
  const [tab, setTab] = useState<TabId>(DEFAULT_TAB)
  const [open, setOpenState] = useState<Folds>(INITIAL_FOLDS)
  const list = useRef<HTMLDivElement>(null)

  const setOpen = useCallback((group: FoldGroup, values: string[]) => {
    setOpenState((prev) => ({ ...prev, [group]: values }))
  }, [])

  // the address decides: on arrival, and when the hash changes (a link, back, forward)
  useEffect(() => {
    const apply = () => {
      const target = parseHash(window.location.hash)
      setTab(target.tab)
      const fold = target.fold
      if (fold) {
        setOpenState((prev) => (prev[fold.group].includes(fold.id)
          ? prev
          : { ...prev, [fold.group]: [...prev[fold.group], fold.id] }))
      }
      if (target.anchor) scrollToAnchor(target.anchor)
    }
    apply()
    window.addEventListener('hashchange', apply)
    window.addEventListener('popstate', apply)
    return () => {
      window.removeEventListener('hashchange', apply)
      window.removeEventListener('popstate', apply)
    }
  }, [])

  // on a phone the tab bar scrolls inside itself: show the active tab (not scrollIntoView, which moves the page too)
  useEffect(() => {
    const bar = list.current
    const active = bar?.querySelector<HTMLElement>('[role=tab][data-state=active]')
    if (!bar || !active) return
    bar.scrollTo({ left: active.offsetLeft - (bar.clientWidth - active.offsetWidth) / 2 })
  }, [tab])

  // a tab click puts the tab in the address, one history entry each
  const choose = (value: string) => {
    if (window.location.hash !== `#${value}`) window.location.hash = value
    else setTab(value as TabId)
  }

  const folds = useMemo<FoldState>(() => ({ open, setOpen }), [open, setOpen])

  return (
    <FoldContext.Provider value={folds}>
      <Tabs value={tab} onValueChange={choose} activationMode="manual" className="gap-4">
        <TabsList ref={list} aria-label="Parts of the Data Model" className="relative h-auto w-full justify-start overflow-x-auto">
          {TABS.map((entry) => (
            <TabsTrigger key={entry.id} value={entry.id} className="flex-none px-3 py-1.5">
              {entry.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((entry) => (
          <TabsContent key={entry.id} value={entry.id} className="space-y-6">
            {panels[entry.id]}
          </TabsContent>
        ))}
      </Tabs>
    </FoldContext.Provider>
  )
}

export type FoldItem = { id: string; title: string; content: ReactNode }

/** Folded sections of one group, each with its anchor; the address can unfold one. */
export function FoldList({ group, items }: { group: FoldGroup; items: FoldItem[] }) {
  const state = useContext(FoldContext)
  const [local, setLocal] = useState<string[]>([])
  const open = state ? state.open[group] : local
  const setOpen = state ? (values: string[]) => state.setOpen(group, values) : setLocal
  return (
    <Accordion type="multiple" value={open} onValueChange={setOpen} className="rounded-md border border-border/70 px-3">
      {items.map((item) => (
        <AccordionItem key={item.id} value={item.id} id={item.id} className="scroll-mt-20">
          <AccordionTrigger className="py-3">{item.title}</AccordionTrigger>
          <AccordionContent className="space-y-3">{item.content}</AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}
