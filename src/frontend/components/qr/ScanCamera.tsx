'use client'

/**
 * The camera frame of the Scan page (plan P11 stage 2, decision 8.118 Q7):
 * one frame for Identify, Locate and Transmit. On a phone the camera starts
 * when the page opens; a tap on the frame or the button starts and stops it.
 */
import { useEffect, useRef, type MutableRefObject } from 'react'
import { Html5QrcodeScanType, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { Camera, CameraOff } from 'lucide-react'

import QRScanner, { type QRScannerRef } from '@/components/qr/QRScanner'
import { Button } from '@/components/ui/button'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { cn } from '@/lib/utils'

export const SCANNER_CONFIG = {
  aspectRatio: 1,
  fps: 10,
  qrbox: { width: 250, height: 250 },
  rememberLastUsedCamera: true,
  supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
  formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
}

export default function ScanCamera({
  scannerRef,
  elementId,
  onScanSuccess,
  onScanError,
  isScanning,
  onStart,
  onStop,
  borderClass = 'border-border',
  message,
  autoStart = true,
  disabled = false,
  children,
}: {
  scannerRef: MutableRefObject<QRScannerRef | null>
  elementId: string
  onScanSuccess: (decodedText: string) => void
  onScanError?: (error: string) => void
  isScanning: boolean
  onStart: () => void
  onStop: () => void
  borderClass?: string
  /** What the frame says while the camera is off. */
  message: string
  /** Start by itself on a phone (a touch screen), where the user came to scan. */
  autoStart?: boolean
  disabled?: boolean
  /** More buttons beside Start / Stop. */
  children?: React.ReactNode
}) {
  const touch = useMediaQuery('(pointer: coarse)')
  const started = useRef(false)
  useEffect(() => {
    if (!autoStart || !touch || started.current) return
    started.current = true
    // the scanner mounts with this component: let it settle first
    const timer = window.setTimeout(onStart, 150)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, touch])

  return (
    <div className="flex w-full max-w-[420px] flex-col items-center gap-2">
      <div
        className={cn('relative aspect-square w-full overflow-hidden rounded-xl border-4 bg-card', borderClass)}
      >
        <QRScanner
          ref={scannerRef}
          elementId={elementId}
          onScanSuccess={onScanSuccess}
          onScanError={onScanError}
          config={SCANNER_CONFIG}
        />
        {!isScanning && (
          <button
            type="button"
            onClick={onStart}
            disabled={disabled}
            className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-muted/70 px-4 text-center text-sm text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Camera className="h-8 w-8" aria-hidden />
            <span className="whitespace-pre-wrap">{message}</span>
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {isScanning ? (
          <Button type="button" variant="outline" size="sm" onClick={onStop} className="gap-1.5">
            <CameraOff className="h-4 w-4" aria-hidden />
            Stop camera
          </Button>
        ) : (
          <Button type="button" variant="outline" size="sm" onClick={onStart} disabled={disabled} className="gap-1.5">
            <Camera className="h-4 w-4" aria-hidden />
            Start camera
          </Button>
        )}
        {children}
      </div>
    </div>
  )
}
