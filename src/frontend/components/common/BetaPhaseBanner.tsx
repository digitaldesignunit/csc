import { getBetaBannerText } from '@/lib/beta'

export default function BetaPhaseBanner() {
  const text = getBetaBannerText()

  return (
    <div
      role="status"
      aria-live="polite"
      className="w-full border-b border-amber-500/50 bg-amber-500/15 px-4 py-2 text-center text-sm font-medium text-amber-950 dark:text-amber-100"
    >
      {text}
    </div>
  )
}
