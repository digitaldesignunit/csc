'use client'

import React, { useState, useRef } from 'react'
import { Html5QrcodeScanType, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { Button } from '@/components/ui/button'
import { CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useRouter } from 'next/navigation'
import { QrCode } from 'lucide-react'
import QRScanner, { QRScannerRef } from '@/components/qr/QRScanner'

type ScanStatus = 'neutral' | 'scanning' | 'found' | 'not_found' | 'error'

const ComponentIdentifier: React.FC = () => {
  const router = useRouter()
  const config = {
    aspectRatio: 1,
    fps: 10,
    qrbox: { width: 300, height: 300 },
    rememberLastUsedCamera: true,
    supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
    formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
  }

  const [scannedID, setScannedID] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus>('neutral')
  const [isChecking, setIsChecking] = useState(false)

  const qrScannerRef = useRef<QRScannerRef | null>(null)
  const elementId = 'identifier-reader'
  const cameraContainerId = 'identifier-cameracontainer'

  const MSG_CAMERA_FEED = 'Camera Feed Placeholder.\n\nScan a QR code to identify a component.'
  const MSG_SCANNING = 'Scanning for QR code...'
  const MSG_FOUND = 'Component found! Opening...'
  const MSG_NOT_FOUND = 'Component not found in database.'
  const MSG_ERROR = 'Error occurred while checking component.'

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

  const handleScannedCode = async (decodedText: string) => {
    setScannedID(decodedText)
    setIsChecking(true)
    setStatus('scanning')
    
    try {
      const exists = await checkComponentExists(decodedText)
      if (exists) {
        setStatus('found')
        // Navigate to component page after a brief delay to show success message
        setTimeout(() => {
          router.push(`/components/${decodedText}`)
        }, 1000)
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
    document.getElementById(elementId)?.scrollIntoView()
    if (!isScanning && qrScannerRef.current) {
      setIsScanning(true)
      setStatus('scanning')
      qrScannerRef.current.startScanning()
    }
  }

  const stopScanning = () => {
    if (qrScannerRef.current) {
      qrScannerRef.current.stopScanning()
      setIsScanning(false)
    }
  }

  const resetScanner = () => {
    if (isScanning) stopScanning()
    setScannedID('')
    setStatus('neutral')
    setIsChecking(false)
  }

  // theme-friendly classes
  const borderClass =
    status === 'found'
      ? 'border-green-500'
      : status === 'not_found' || status === 'error'
      ? 'border-destructive'
      : status === 'scanning'
      ? 'border-blue-500'
      : 'border-border'

  const statusBadgeClass =
    status === 'found'
      ? 'bg-green-500 text-white'
      : status === 'not_found' || status === 'error'
      ? 'bg-destructive text-destructive-foreground'
      : status === 'scanning'
      ? 'bg-blue-500 text-white'
      : 'bg-muted text-muted-foreground'

  const getStatusMessage = () => {
    if (isChecking) return 'Checking component...'
    switch (status) {
      case 'scanning': return MSG_SCANNING
      case 'found': return MSG_FOUND
      case 'not_found': return MSG_NOT_FOUND
      case 'error': return MSG_ERROR
      default: return MSG_CAMERA_FEED
    }
  }

  return (
    <div className="flex flex-col items-center">
      {scannedID ? (
        <CardHeader className="relative w-full max-w-sm p-1 pb-3">
          <div className="grid w-full grid-cols-2 items-center gap-y-3">
            <span className="text-sm font-medium text-foreground">Component ID:</span>
            <div className="flex justify-end items-center">
              <Badge variant="secondary" className={`flex-shrink-0 ${statusBadgeClass}`}>
                {scannedID}
              </Badge>
            </div>
          </div>
        </CardHeader>
      ) : null}

      {/* QR Code Scanner Canvas */}
      <CardContent
        id={cameraContainerId}
        className={`mt-4 p-0 relative w-full max-w-[500px] h-[500px] border-8 rounded-xl ${borderClass} bg-card`}
      >
        <QRScanner
          ref={qrScannerRef}
          elementId={elementId}
          onScanSuccess={handleScannedCode}
          config={config}
        />
        {!isScanning && (
          <div className="absolute inset-0 bg-muted/60 flex items-center justify-center text-center rounded">
            <span className="whitespace-pre-wrap text-sm text-muted-foreground">
              {getStatusMessage()}
            </span>
          </div>
        )}
      </CardContent>

      <div className="m-4 flex flex-col items-center space-y-3">
        {!isScanning && status !== 'found' && (
          <Button 
            onClick={startScanning} 
            variant="outline" 
            className="w-[200px] flex items-center gap-2"
            disabled={isChecking}
          >
            <QrCode className="h-4 w-4" />
            Start QR Code Scan
          </Button>
        )}
        {isScanning && (
          <Button onClick={stopScanning} variant="outline" className="w-[200px]">
            Stop Scanning
          </Button>
        )}
        {!isScanning && status !== 'found' && (
          <Button onClick={resetScanner} variant="destructive" className="w-[200px]">
            Reset
          </Button>
        )}
      </div>
    </div>
  )
}

export default ComponentIdentifier
