'use client'

import React, { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Search } from 'lucide-react'

import ScanCamera from '@/components/qr/ScanCamera'
import { type QRScannerRef } from '@/components/qr/QRScanner'
import UnknownTagLink from '@/components/snapshot/UnknownTagLink'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { uuidFromScan } from '@/lib/scanIds'

type ScanStatus = 'neutral' | 'scanning' | 'found' | 'not_found' | 'error'

/** Scan mode "Identify": the tag of a physical piece opens its digital twin. */
const ComponentIdentifier: React.FC = () => {
  const router = useRouter()
  const [scannedID, setScannedID] = useState('')
  const [typed, setTyped] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus>('neutral')
  const [isChecking, setIsChecking] = useState(false)

  const qrScannerRef = useRef<QRScannerRef | null>(null)

  const checkComponentExists = async (identityId: string): Promise<boolean> => {
    try {
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}?expand=shallow`,
        { credentials: 'include', cache: 'no-store' },
      )
      return response.ok
    } catch (error) {
      console.error('Error checking component:', error)
      return false
    }
  }

  const stopScanning = () => {
    if (qrScannerRef.current) {
      void qrScannerRef.current.stopScanning()
      setIsScanning(false)
    }
  }

  const handleScannedCode = async (scanned: string) => {
    const decodedText = uuidFromScan(scanned) ?? scanned.trim()
    if (!decodedText) return
    setScannedID(decodedText)
    setIsChecking(true)
    setStatus('scanning')
    try {
      if (await checkComponentExists(decodedText)) {
        setStatus('found')
        router.push(`/components/${decodedText}`)
      } else {
        setStatus('not_found')
      }
    } catch (error) {
      console.error('Error checking component:', error)
      setStatus('error')
    } finally {
      setIsChecking(false)
      stopScanning()
    }
  }

  const startScanning = () => {
    if (!isScanning && qrScannerRef.current) {
      setIsScanning(true)
      setStatus('scanning')
      void qrScannerRef.current.startScanning()
    }
  }

  const borderClass =
    status === 'found'
      ? 'border-green-500'
      : status === 'not_found' || status === 'error'
        ? 'border-destructive'
        : status === 'scanning'
          ? 'border-blue-500'
          : 'border-border'

  const message = isChecking
    ? 'Checking...'
    : status === 'found'
      ? 'Found. Opening...'
      : 'Tap to start the camera and scan a tag.'

  return (
    <div className="flex flex-col items-center gap-3">
      <ScanCamera
        scannerRef={qrScannerRef}
        elementId="identifier-reader"
        onScanSuccess={handleScannedCode}
        onScanError={() => {
          setStatus('error')
          setIsScanning(false)
        }}
        isScanning={isScanning}
        onStart={startScanning}
        onStop={stopScanning}
        borderClass={borderClass}
        message={message}
        disabled={isChecking}
      />

      <form
        className="flex w-full max-w-[420px] gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void handleScannedCode(typed)
        }}
      >
        <Input
          aria-label="Paste an id or a link"
          placeholder="or paste an id or a link"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <Button type="submit" variant="outline" disabled={!typed.trim() || isChecking} className="gap-1.5">
          <Search className="h-4 w-4" aria-hidden />
          Open
        </Button>
      </form>

      {status === 'not_found' && (
        <div className="w-full max-w-[420px] text-center text-sm">
          <p className="text-destructive">No component with this id.</p>
          <UnknownTagLink id={scannedID} className="mt-1 text-xs text-muted-foreground" />
        </div>
      )}
      {status === 'error' && (
        <p className="text-sm text-destructive">The camera or the lookup failed. Try again or paste the id.</p>
      )}
    </div>
  )
}

export default ComponentIdentifier
