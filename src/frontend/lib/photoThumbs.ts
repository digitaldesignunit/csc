/**
 * Thumbnails of the compact photo row (the "Photos and location" card, decision
 * 8.118): one fixed height, the width follows the photo's own aspect ratio
 * (clamped to 3:4 .. 16:9, cropped only beyond that), left-aligned and
 * wrapping, so two photos never stretch into wide flat strips. The height is
 * a CSS variable so the width limits follow it.
 */
export const THUMB_MIN_RATIO = 3 / 4
export const THUMB_MAX_RATIO = 16 / 9

/** Beyond this many photos the row scrolls sideways inside the card. */
export const THUMB_WRAP_LIMIT = 3

/** The row: wraps inside the card; with many photos it scrolls inside the card, never the page. */
export const thumbRow = (count: number) =>
  count > THUMB_WRAP_LIMIT
    ? 'flex flex-nowrap items-start gap-2 overflow-x-auto pb-1'
    : 'flex flex-wrap items-start gap-2'

/** One thumbnail box: 128 px high on a phone, 176 px from sm. */
export const THUMB_BOX =
  'group relative h-[var(--th)] max-w-full shrink-0 overflow-hidden rounded-md border border-border bg-muted [--th:8rem] sm:[--th:11rem]'

/** The picture: natural width at the box height, clamped. */
export const THUMB_IMG =
  'block h-full w-auto min-w-[calc(var(--th)*0.75)] max-w-[calc(var(--th)*1.7778)] object-cover transition-opacity group-hover:opacity-90'
