'use client'

import { useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import ComponentIdentifier from '@/components/components/ComponentIdentifier'
import ComponentLocateById from '@/components/components/ComponentLocateById'
import ComponentIdTransmitter from '@/components/idtransmission/ComponentIdTransmitter'
import Help from '@/components/ui/help'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

export const SCAN_MODES = [
  {
    value: 'identify',
    label: 'Identify',
    help: 'Scan the QR code of a physical piece. The matching digital piece opens with its catalog data, geometry and records.',
  },
  {
    value: 'locate',
    label: 'Locate',
    help: 'Find the physical part of a digital piece. Set its id first (scan it or paste it), then scan physical tags until one matches.',
  },
  {
    value: 'transmit',
    label: 'Transmit',
    help: 'Send a scanned id to your open CAD session (Grasshopper). The id waits in a queue until the CAD side picks it up.',
  },
] as const
type ScanMode = (typeof SCAN_MODES)[number]['value']

function parseMode(value: string | null | undefined, hasReference: boolean): ScanMode {
  const found = SCAN_MODES.find((m) => m.value === value)
  if (found) return found.value
  return hasReference ? 'locate' : 'identify'
}

/** The Scan page: a mode switch, one camera frame, the paste field under it. */
export default function ScanPageClient({
  initialMode,
  referenceId,
}: {
  initialMode: string
  referenceId?: string
}) {
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const [mode, setMode] = useState<ScanMode>(parseMode(initialMode, Boolean(referenceId)))
  const current = SCAN_MODES.find((m) => m.value === mode) ?? SCAN_MODES[0]

  const change = (value: string) => {
    if (!value) return
    const next = parseMode(value, false)
    setMode(next)
    const params = new URLSearchParams(search.toString())
    params.set('mode', next)
    if (next !== 'locate') params.delete('reference_id')
    router.replace(`${pathname}?${params.toString()}`, { scroll: false })
  }

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-4 p-3 sm:p-6">
      <div className="flex items-center gap-2">
        <ToggleGroup
          type="single"
          variant="outline"
          value={mode}
          onValueChange={change}
          aria-label="Scan mode"
        >
          {SCAN_MODES.map((m) => (
            <ToggleGroupItem key={m.value} value={m.value} className="px-4">
              {m.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Help label={current.label} text={current.help} />
      </div>
      {/* one camera at a time: a mode mounts its own frame */}
      {mode === 'identify' && <ComponentIdentifier key="identify" />}
      {mode === 'locate' && <ComponentLocateById key="locate" presetReferenceID={referenceId} />}
      {mode === 'transmit' && <ComponentIdTransmitter key="transmit" />}
    </div>
  )
}
