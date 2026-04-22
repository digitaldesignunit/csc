'use client'

import React, { useState, useRef, useEffect } from 'react'
import { Html5QrcodeScanType, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { Button } from '@/components/ui/button'
import { CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import QRScanner, { QRScannerRef } from '@/components/qr/QRScanner'

interface Props {
  presetReferenceID?: string
}

type ScanStatus = 'neutral' | 'ok' | 'bad'

const ComponentLocateById: React.FC<Props> = ({ presetReferenceID }) => {
  const config = {
    aspectRatio: 1,
    fps: 10,
    qrbox: { width: 300, height: 300 },
    rememberLastUsedCamera: true,
    supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
    formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
  }

  const [referenceID, setReferenceID] = useState(presetReferenceID || '')
  const [currentID, setCurrentID] = useState('')
  const [inputReferenceID, setInputReferenceID] = useState('')
  const [comparisonResult, setComparisonResult] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus>('neutral')

  const qrScannerRef = useRef<QRScannerRef | null>(null)
  const elementId = 'reader'
  const cameraContainerId = 'cameracontainer'

  const MSG_MATCH = 'IDs Match!'
  const MSG_MISMATCH = 'Does not match the Reference ID!'
  const MSG_REF_SCANNED = 'Reference ID set.\nStart scan for comparison.'
  const MSG_CAMERA_FEED =
    'Camera Feed Placeholder.\n\nTo start comparing IDs,\neither scan or type an ID as reference.'

  // Handle preset reference ID
  useEffect(() => {
    if (presetReferenceID && presetReferenceID === referenceID && !comparisonResult) {
      setStatus('ok')
      setComparisonResult(MSG_REF_SCANNED)
    }
  }, [presetReferenceID, referenceID, comparisonResult])

  const startScanningForReference = () => {
    document.getElementById(elementId)?.scrollIntoView()
    if (!referenceID && !isScanning && qrScannerRef.current) {
      setIsScanning(true)
      qrScannerRef.current.startScanning()
    }
  }

  const startScanningForComparison = () => {
    document.getElementById(elementId)?.scrollIntoView()
    if (referenceID && !isScanning && qrScannerRef.current) {
      setIsScanning(true)
      qrScannerRef.current.startScanning()
    }
  }

  const stopScanning = () => {
    if (qrScannerRef.current) {
      qrScannerRef.current.stopScanning()
      setIsScanning(false)
    }
  }

  const handleQRScanSuccess = (decodedText: string) => {
    if (!referenceID) {
      // Scanning for reference
      setReferenceID(decodedText)
      setStatus('ok')
      setComparisonResult(MSG_REF_SCANNED)
      stopScanning()
    } else {
      // Scanning for comparison
      const match = decodedText === referenceID
      setCurrentID(decodedText)
      setStatus(match ? 'ok' : 'bad')
      setComparisonResult(match ? MSG_MATCH : MSG_MISMATCH)
      if (match) stopScanning()
    }
  }

  const handleQRScanError = (error: string) => {
    console.error('QR scan error:', error)
    setStatus('bad')
    setIsScanning(false)
  }

  const resetScanner = () => {
    if (isScanning) stopScanning()
    setReferenceID('')
    setComparisonResult('')
    setCurrentID('')
    setInputReferenceID('')
    setStatus('neutral')
  }

  const handleSetInputReferenceID = () => {
    if (!inputReferenceID.trim()) return
    setReferenceID(inputReferenceID.trim())
    setComparisonResult(MSG_REF_SCANNED)
    setStatus('ok')
  }

  // theme-friendly classes
  const borderClass =
    status === 'ok'
      ? 'border-green-500'
      : status === 'bad'
      ? 'border-destructive'
      : 'border-border'

  const currentBadgeClass =
    status === 'ok'
      ? 'bg-green-500 text-white'
      : status === 'bad'
      ? 'bg-destructive text-destructive-foreground'
      : 'bg-muted text-muted-foreground'

  const refBadgeClass =
    referenceID
      ? 'bg-primary text-primary-foreground'
      : 'bg-muted text-muted-foreground'

  return (
    <div className="flex flex-col items-center">
      <CardHeader className="relative w-full max-w-sm p-1">
        {/* Set Reference ID Interface */}
        {!referenceID && !isScanning && (
          <div className="flex w-full max-w-sm flex-col gap-2 pb-4">
            {/* input ABOVE the button */}
            <Input
              id="inputFieldReferenceID"
              placeholder="Reference ID"
              value={inputReferenceID}
              onChange={(e) => setInputReferenceID(e.target.value)}
            />
            <Button variant="outline" onClick={handleSetInputReferenceID}>
              Set Ref. ID
            </Button>
          </div>
        )}

        {/* Display Reference and Current ID */}
        <div className="w-full grid grid-cols-2 gap-y-3 items-center">
          <div className="flex justify-start min-w-0 w-20">
            <span className="text-sm font-medium text-foreground">Ref. ID:</span>
          </div>
          <div className="flex justify-end items-center">
            <Badge variant="secondary" className={`no-wrap flex-shrink-0 ${refBadgeClass}`}>
              {referenceID || 'Not set'}
            </Badge>
          </div>

          <div className="flex justify-start min-w-0 w-20">
            <span className="text-sm font-medium text-foreground">Cur. ID:</span>
          </div>
          <div className="flex justify-end items-center">
            <Badge variant="secondary" className={`no-wrap flex-shrink-0 ${currentBadgeClass}`}>
              {currentID || 'Not set'}
            </Badge>
          </div>
        </div>
      </CardHeader>

      {/* QR Code Scanner Canvas */}
      <CardContent
        id={cameraContainerId}
        className={`mt-4 p-0 relative w-full max-w-[500px] h-[500px] border-8 rounded-xl ${borderClass} bg-card`}
      >
        <QRScanner
          ref={qrScannerRef}
          elementId={elementId}
          onScanSuccess={handleQRScanSuccess}
          onScanError={handleQRScanError}
          config={config}
        />
        {!isScanning && (
          <div className="absolute inset-0 bg-muted/60 flex items-center justify-center text-center rounded">
            <span className="whitespace-pre-wrap text-sm text-muted-foreground">
              {comparisonResult ? comparisonResult : MSG_CAMERA_FEED}
            </span>
          </div>
        )}
      </CardContent>

      <div className="m-4 flex flex-col items-center space-y-3">
        {!referenceID && (
          <Button onClick={startScanningForReference} variant="outline" className="w-[200px]">
            Start QR Code Scan
          </Button>
        )}
        {referenceID && !isScanning && (
          <Button onClick={startScanningForComparison} variant="outline" className="w-[200px]">
            Start QR Code Scan
          </Button>
        )}
        {isScanning && (
          <Button onClick={stopScanning} variant="outline" className="w-[200px]">
            Stop Scanning
          </Button>
        )}
        {!isScanning && (
          <Button onClick={resetScanner} variant="destructive" className="w-[200px]">
            Reset
          </Button>
        )}
      </div>
    </div>
  )
}

export default ComponentLocateById
