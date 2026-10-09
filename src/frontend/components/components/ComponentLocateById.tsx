'use client'

import React, { useState, useRef } from 'react'
import { RotateCcw } from 'lucide-react'

import ScanCamera from '@/components/qr/ScanCamera'
import { type QRScannerRef } from '@/components/qr/QRScanner'
import UnknownTagLink from '@/components/snapshot/UnknownTagLink'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { uuidFromScan } from '@/lib/scanIds'

interface Props {
  presetReferenceID?: string
}

type ScanStatus = 'neutral' | 'ok' | 'bad'

/**
 * Scan mode "Locate": set the id of a digital piece as the reference, then
 * scan physical tags until one matches.
 */
const ComponentLocateById: React.FC<Props> = ({ presetReferenceID }) => {
  const preset = uuidFromScan(presetReferenceID) ?? (presetReferenceID?.trim() || '')
  const [referenceID, setReferenceID] = useState(preset)
  const [currentID, setCurrentID] = useState('')
  const [typed, setTyped] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus>(preset ? 'ok' : 'neutral')

  const qrScannerRef = useRef<QRScannerRef | null>(null)

  const startScanning = () => {
    if (!isScanning && qrScannerRef.current) {
      setIsScanning(true)
      void qrScannerRef.current.startScanning()
    }
  }

  const stopScanning = () => {
    if (qrScannerRef.current) {
      void qrScannerRef.current.stopScanning()
      setIsScanning(false)
    }
  }

  /** A scanned or pasted id: the reference first, then the ones to compare. */
  const take = (text: string, scanned: boolean) => {
    const id = uuidFromScan(text) ?? text.trim()
    if (!id) return
    if (!referenceID) {
      setReferenceID(id)
      setStatus('ok')
      if (scanned) stopScanning()
      return
    }
    const match = id.toLowerCase() === referenceID.toLowerCase()
    setCurrentID(id)
    setStatus(match ? 'ok' : 'bad')
    if (match && scanned) stopScanning()
  }

  const reset = () => {
    if (isScanning) stopScanning()
    setReferenceID('')
    setCurrentID('')
    setTyped('')
    setStatus('neutral')
  }

  const matched = Boolean(referenceID && currentID) && status === 'ok'
  const borderClass = status === 'ok' && matched
    ? 'border-green-500'
    : status === 'bad'
      ? 'border-destructive'
      : 'border-border'
  const message = !referenceID
    ? 'Scan or paste the id of the piece you look for.'
    : 'Tap to start the camera and scan tags until one matches.'

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="grid w-full max-w-[420px] grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1.5 text-sm">
        <span className="font-medium">Looking for</span>
        <Badge
          variant="secondary"
          className={`min-w-0 justify-self-end break-all ${referenceID ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
        >
          {referenceID || 'not set'}
        </Badge>
        <span className="font-medium">Scanned</span>
        <Badge
          variant="secondary"
          className={`min-w-0 justify-self-end break-all ${
            matched ? 'bg-green-500 text-white' : status === 'bad' ? 'bg-destructive text-destructive-foreground' : 'bg-muted text-muted-foreground'
          }`}
        >
          {currentID || 'nothing yet'}
        </Badge>
      </div>

      {matched && (
        <p className="text-sm font-medium text-green-700 dark:text-green-300" role="status">
          This is the piece you look for.
        </p>
      )}
      {status === 'bad' && (
        <p className="text-sm text-destructive" role="status">
          This is not the piece you look for.
        </p>
      )}

      <ScanCamera
        scannerRef={qrScannerRef}
        elementId="locate-reader"
        onScanSuccess={(text) => take(text, true)}
        onScanError={() => {
          setStatus('bad')
          setIsScanning(false)
        }}
        isScanning={isScanning}
        onStart={startScanning}
        onStop={stopScanning}
        borderClass={borderClass}
        message={message}
        // with a reference from a link the camera has a purpose at once
        autoStart
      >
        {(referenceID || currentID) && !isScanning && (
          <Button type="button" variant="ghost" size="sm" onClick={reset} className="gap-1.5">
            <RotateCcw className="h-4 w-4" aria-hidden />
            Start over
          </Button>
        )}
      </ScanCamera>

      <form
        className="flex w-full max-w-[420px] gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          take(typed, false)
          setTyped('')
        }}
      >
        <Input
          aria-label={referenceID ? 'Paste an id to compare' : 'Paste the id you look for'}
          placeholder={referenceID ? 'or paste an id to compare' : 'or paste the id you look for'}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <Button type="submit" variant="outline" disabled={!typed.trim()}>
          {referenceID ? 'Compare' : 'Set'}
        </Button>
      </form>

      <UnknownTagLink id={referenceID} className="w-full max-w-[420px] text-center text-xs text-muted-foreground" />
    </div>
  )
}

export default ComponentLocateById
