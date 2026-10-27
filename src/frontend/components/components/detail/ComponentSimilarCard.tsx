'use client'

/**
 * The "Similar pieces" card of the component page (decision 8.174): the six
 * pieces nearest to this one in the full radial signature, with a small
 * thumbnail, the name and one line; "Show more" lists up to 24 and is offered
 * only when a seventh neighbour exists. The card sits in the left rail on a wide
 * screen (three tiles to a row), so the tiles are small. They are pieces
 * this viewer may see and that are in circulation, ranked by distance in the
 * standardised descriptor space, not by position on the similarity map. The
 * card leaves no trace when there is nothing to show: the piece has no
 * descriptor, the matrix is not built, or no other piece is visible.
 */
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Shapes } from 'lucide-react'

import Help from '@/components/ui/help'
import { Button } from '@/components/ui/button'
import type { SimilarPiece, SimilarPieces } from '@/generated/CatalogModels'
import { backendJson } from '@/lib/backend'
import { rowName } from '@/lib/browse'
import {
  SIMILAR_MORE_COUNT,
  cardOfAnswer,
  cardOfError,
  neighbourLine,
  neighbourTitle,
  needsScrollBack,
  shownPieces,
  similarPath,
  toggleLabel,
  type SimilarCard,
} from '@/lib/similarPieces'
import ComponentPreviewImage from '../ComponentPreviewImage'

const HELP = 'The pieces whose shape is closest to this one, compared over the whole radial signature of '
  + 'each piece (not the two-dimensional similarity map). Similar in outline and size: the signature '
  + 'measures distances from the centre of the piece. Only pieces in circulation that you may see are compared.'

function Neighbour({ item }: { item: SimilarPiece }) {
  const row = item.piece
  const snapshotId = row.has_preview !== false && row.current_snapshot_id ? row.current_snapshot_id : null
  return (
    <li className="min-w-0">
      <Link
        href={`/components/${row._id}`}
        title={neighbourTitle(item)}
        className="block rounded-md border border-border bg-background p-1 hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <ComponentPreviewImage
          snapshot_id={snapshotId}
          alt={`Preview of ${rowName(row)}`}
          width={88}
          height={60}
          maxHeight={60}
          className="mx-auto rounded"
        />
        <span className="mt-1 block truncate text-[11px] font-medium leading-tight">{rowName(row)}</span>
        <span className="block truncate text-[10px] leading-tight text-muted-foreground">{neighbourLine(row)}</span>
      </Link>
    </li>
  )
}

export default function ComponentSimilarCard({ identityId }: { identityId: string }) {
  const [card, setCard] = useState<SimilarCard | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [loadedMore, setLoadedMore] = useState(false)
  const top = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setCard(null)
    setExpanded(false)
    setLoadedMore(false)
    backendJson<SimilarPieces>(similarPath(identityId), { signal: controller.signal })
      .then((answer) => setCard(cardOfAnswer(answer)))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setCard(cardOfError(error))
      })
    return () => controller.abort()
  }, [identityId])

  const showMore = () => {
    if (loadedMore) {
      setExpanded(true)
      return
    }
    backendJson<SimilarPieces>(similarPath(identityId, SIMILAR_MORE_COUNT))
      .then((answer) => {
        const more = cardOfAnswer(answer)
        if (more.kind !== 'list') return
        setCard(more)
        setLoadedMore(true)
        setExpanded(true)
      })
      .catch(() => undefined)   // the six stay
  }

  const showFewer = () => {
    setExpanded(false)
    const element = top.current
    if (element && needsScrollBack(element.getBoundingClientRect().top)) {
      element.scrollIntoView({ block: 'start' })
    }
  }

  if (!card || card.kind === 'hidden') return null
  const label = toggleLabel(card.pieces.length, expanded)

  return (
    <section ref={top} aria-label="Similar pieces"
      className="scroll-mt-3 rounded-lg border border-border bg-card p-2.5 shadow-sm">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Shapes className="h-4 w-4" aria-hidden />
        Similar pieces
        <Help label="Similar pieces" text={HELP} />
      </h2>
      <ul className="grid grid-cols-3 gap-1.5 sm:grid-cols-6 lg:grid-cols-3">
        {shownPieces(card.pieces, expanded).map((item) => <Neighbour key={item.piece._id} item={item} />)}
      </ul>
      {label && (
        <Button type="button" variant="ghost" size="sm" className="mt-2 h-7 text-xs" aria-expanded={expanded}
          onClick={expanded ? showFewer : showMore}>
          {label}
        </Button>
      )}
    </section>
  )
}
