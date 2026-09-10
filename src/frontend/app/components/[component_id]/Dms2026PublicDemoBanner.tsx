import Link from 'next/link'
import { resolveStatic } from '@/lib/utils'

/**
 * TEMPORARY — Design Modelling Symposium 2026 public-demo banners.
 * Delete this file, `public/logo/dms26.png`, and the `publicDemoBanner`
 * wiring in `page.tsx` after the event.
 *
 * Local/dev uses the bundled copy in `public/logo/` (same as the DDU logos).
 * Production Apache also has `csc_assets/static/logo/dms26.png`.
 */

const RUBBLE_ID = '04c4fbc4-af09-4566-9935-33e81df39200'
const BEAM_ID = '2c9c39ff-eae4-4adc-9fae-6dd4bb71420b'

const BANNERS: Record<string, { href: string; label: string }> = {
  [RUBBLE_ID]: {
    href: `/components/${BEAM_ID}`,
    label: 'Reclaimed Concrete Beam from the ZirKuS Project',
  },
  [BEAM_ID]: {
    href: `/components/${RUBBLE_ID}`,
    label: 'Scanned Rubble Component',
  },
}

function dms26BackgroundSrc() {
  const filePath = '/logo/dms26.png'
  return resolveStatic(filePath)
}

export function getDms2026PublicDemoBanner(identityId: string) {
  const peer = BANNERS[identityId]
  if (!peer) return undefined

  return (
    <div
      key="dms2026-public-demo-banner"
      role="status"
      className="relative [grid-area:banner] overflow-hidden rounded-lg px-4 py-3 text-white"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={dms26BackgroundSrc()}
        alt=""
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0" />
      <div className="relative">
        <p className="font-medium">Design Modelling Symposium 2026 - Public Demo View</p>
        <p className="mt-1 text-sm text-white/90">
          This component is shared without login, feel free to also explore other public components:
        </p>
        <ul className="mt-1 list-disc pl-5 text-sm text-white/90">
          <li>
            <Link
              href={peer.href}
              className="font-medium underline underline-offset-4 hover:no-underline"
            >
              {peer.label}
            </Link>
          </li>
        </ul>
        <p className="mt-3 text-sm text-white/90">
          <Link
            href="/auth/signin"
            className="font-medium underline underline-offset-4 hover:no-underline"
          >
            Sign in
          </Link>{' '}
          for catalog actions and reservation workflows.
        </p>
      </div>
    </div>
  )
}
