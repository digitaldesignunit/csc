'use client'

/**
 * A tag id: typed or pasted (an id or any link that ends in one, spec 7.5)
 * or scanned from the QR code on the piece. Calls `onChange` with the id
 * once it reads as one, or with the raw text while it does not.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Html5QrcodeScanType, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { QrCode, X } from 'lucide-react'

import QRScanner, { type QRScannerRef } from '@/components/qr/QRScanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { uuidFromScan } from '@/lib/scanIds'

export function TagField({
  id,
  value,
  onChange,
  onScan,
  placeholder = 'Id or link',
  disabled,
  autoScan = false,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  /** Called with the id of a scanned code (after `onChange`). */
  onScan?: (id: string) => void
  placeholder?: string
  disabled?: boolean
  /** On a touch screen open the camera first, the paste field second (decision 8.118 S5). */
  autoScan?: boolean
}) {
  const scanner = useRef<QRScannerRef | null>(null)
  const [scanning, setScanning] = useState(false)
  const readerId = `${id}-reader`
  const config = useMemo(
    () => ({
      aspectRatio: 1,
      fps: 10,
      qrbox: { width: 240, height: 240 },
      rememberLastUsedCamera: true,
      supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
      formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
    }),
    [],
  )

  const stop = useCallback(async () => {
    await scanner.current?.stopScanning()
    setScanning(false)
  }, [])

  const found = useCallback(
    (text: string) => {
      const read = uuidFromScan(text)
      onChange(read ?? text.trim())
      if (read) onScan?.(read)
      void stop()
    },
    [onChange, onScan, stop],
  )

  const start = () => {
    setScanning(true)
    // the reader element exists once the state is set
    window.setTimeout(() => {
      document.getElementById(readerId)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      void scanner.current?.startScanning()
    }, 0)
  }

  const touch = useMediaQuery('(pointer: coarse)')
  const offered = useRef(false)
  useEffect(() => {
    if (!autoScan || !touch || offered.current || disabled || uuidFromScan(value)) return
    offered.current = true
    // the reader element exists once the state is set
    const timer = window.setTimeout(() => start(), 150)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoScan, touch])

  const clean = uuidFromScan(value)
  return (
    <div className={autoScan && scanning ? 'flex flex-col-reverse gap-2' : 'space-y-2'}>
      <div className="flex gap-2">
        <Input
          id={id}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(uuidFromScan(event.target.value) ?? event.target.value)}
          placeholder={placeholder}
          className="font-mono text-xs"
          autoComplete="off"
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={disabled}
          onClick={() => (scanning ? void stop() : start())}
          aria-label={scanning ? 'Stop scanning' : 'Scan the QR code'}
        >
          {scanning ? <X className="h-4 w-4" /> : <QrCode className="h-4 w-4" />}
        </Button>
      </div>
      {value.trim() && !clean && (
        <p className="text-xs text-destructive">Not an id: give the UUID on the tag or a link that ends in it.</p>
      )}
      <div className={scanning ? 'mx-auto w-full max-w-[320px]' : 'hidden'}>
        <QRScanner ref={scanner} elementId={readerId} onScanSuccess={found} config={config} />
      </div>
    </div>
  )
}
