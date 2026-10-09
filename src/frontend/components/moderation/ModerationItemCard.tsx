'use client'

/**
 * One card anatomy for everything a moderator or reviewer decides on (plan P11
 * stage 3, decision 8.118): header (title, version or method, chips, Open),
 * one muted meta line, a two-column facts grid, and a footer with the
 * decisions in a fixed order (secondary left of primary). A decision that
 * needs a text (a reject reason, the note of an accreditation) opens its
 * field inside the card. The Snapshots, Evidence and Verification tabs all
 * use it, so they cannot drift apart.
 */
import { useState, type ReactNode } from 'react'
import Link from 'next/link'
import { ExternalLink, type LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { truncateNote, type Fact } from '@/lib/moderationCard'

export type CardChip = { label: string; variant?: 'secondary' | 'outline' }

export type CardAction = {
  key: string
  label: string
  icon?: LucideIcon
  /** primary: the one decision to take; outline: the other; destructive: outline in red; icon: a quiet icon button (delete). */
  kind: 'primary' | 'outline' | 'destructive' | 'icon'
  /** Throws to keep the card as it is (the caller has told the user why). */
  run: (text: string) => Promise<void> | void
  /** The action asks for a text first, in the card. */
  text?: { label: string; placeholder: string; required: boolean }
  /** Confirm through the browser before running (a delete). */
  confirm?: string
  disabled?: boolean
}

type Props = {
  title: string
  /** "v2" or the method of an evidence record. */
  sub?: string
  chips: CardChip[]
  openHref: string
  meta: string
  facts: Fact[]
  note?: string | null
  warning?: string | null
  actions: CardAction[]
  children?: ReactNode
}

export default function ModerationItemCard({
  title, sub, chips, openHref, meta, facts, note, warning, actions, children,
}: Props) {
  const [asking, setAsking] = useState<CardAction | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [more, setMore] = useState(false)

  const execute = async (action: CardAction, given: string) => {
    setBusy(true)
    try {
      await action.run(given)
      setAsking(null)
      setText('')
    } catch {
      // the caller has shown the reason; the card stays as it is
    } finally {
      setBusy(false)
    }
  }

  const click = (action: CardAction) => {
    if (action.text) {
      setAsking(action)
      setText('')
      return
    }
    if (action.confirm && !window.confirm(action.confirm)) return
    void execute(action, '')
  }

  const shownNote = note ? truncateNote(note) : null

  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-sm">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1.5 sm:flex-1">
            <h3 className="flex flex-wrap items-baseline gap-x-2 text-base font-semibold leading-tight">
              <span>{title}</span>
              {sub && <span className="text-sm font-normal text-muted-foreground">{sub}</span>}
            </h3>
            <div className="flex flex-wrap items-center gap-1.5">
              {chips.map((chip) => (
                <Badge key={chip.label} variant={chip.variant ?? 'outline'} className="font-normal">{chip.label}</Badge>
              ))}
            </div>
          </div>
          <Button asChild variant="outline" size="sm" className="w-full sm:w-auto sm:shrink-0">
            <Link href={openHref}>Open <ExternalLink className="h-3.5 w-3.5" aria-hidden /></Link>
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">{meta}</p>

        {warning && <p className="text-xs text-amber-800 dark:text-amber-200" role="status">{warning}</p>}

        {facts.length > 0 && (
          <dl className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2">
            {facts.map((fact) => (
              <div
                key={fact.label}
                className={`grid grid-cols-[5.5rem_minmax(0,1fr)] items-baseline gap-x-3 ${fact.value.length > 48 ? 'sm:col-span-2' : ''}`}
              >
                <dt className="text-xs text-muted-foreground">{fact.label}</dt>
                <dd className="min-w-0 whitespace-pre-line break-words">{fact.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {shownNote && (
          <p className="text-xs text-muted-foreground">
            {more && note ? note : shownNote.text}
            {shownNote.more && (
              <>
                {' '}
                <button type="button" className="underline underline-offset-4" onClick={() => setMore((v) => !v)}>
                  {more ? 'less' : 'more'}
                </button>
              </>
            )}
          </p>
        )}

        {children}

        {actions.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            {asking?.text ? (
              <div className="space-y-2">
                <label className="text-xs font-medium" htmlFor={`ask-${asking.key}`}>{asking.text.label}</label>
                <Textarea
                  id={`ask-${asking.key}`}
                  rows={2}
                  autoFocus
                  value={text}
                  placeholder={asking.text.placeholder}
                  onChange={(event) => setText(event.target.value)}
                />
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setAsking(null)}>Cancel</Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={asking.kind === 'destructive' ? 'destructive' : 'default'}
                    disabled={busy || (asking.text.required && !text.trim())}
                    onClick={() => void execute(asking, text.trim())}
                  >
                    {asking.label}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-end gap-2">
                {actions.map((action) => {
                  const Icon = action.icon
                  if (action.kind === 'icon') {
                    return (
                      <Button
                        key={action.key}
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="mr-auto text-destructive hover:text-destructive"
                        aria-label={action.label}
                        title={action.label}
                        disabled={busy || action.disabled}
                        onClick={() => click(action)}
                      >
                        {Icon && <Icon className="h-4 w-4" aria-hidden />}
                      </Button>
                    )
                  }
                  return (
                    <Button
                      key={action.key}
                      type="button"
                      size="sm"
                      variant={action.kind === 'primary' ? 'default' : 'outline'}
                      className={action.kind === 'destructive' ? 'border-destructive/50 text-destructive hover:text-destructive' : undefined}
                      disabled={busy || action.disabled}
                      onClick={() => click(action)}
                    >
                      {Icon && <Icon className="h-4 w-4" aria-hidden />}
                      {action.label}
                    </Button>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
