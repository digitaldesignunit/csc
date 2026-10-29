/**
 * Scroll to the card of an evidence record and ring it for 1.8 s. The card may
 * not be in the document yet (the records load, a section opens), so the
 * lookup is tried for about two seconds. True when the card was found.
 * `smooth: false` for the arrival on a page, where the layout is still settling.
 */
export function scrollToRecord(recordId: string, { tries = 40, smooth = true } = {}): Promise<boolean> {
  return new Promise((resolve) => {
    const attempt = (left: number) => {
      const card = document.getElementById(`record-${recordId}`)
      if (card) {
        card.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'center' })
        card.classList.add('ring-2', 'ring-primary')
        window.setTimeout(() => card.classList.remove('ring-2', 'ring-primary'), 1800)
        resolve(true)
      } else if (left <= 0) {
        resolve(false)
      } else {
        window.setTimeout(() => attempt(left - 1), 50)
      }
    }
    attempt(tries)
  })
}
