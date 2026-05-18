'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Html5QrcodeScanType,
  Html5QrcodeSupportedFormats,
} from 'html5-qrcode'
import { AlertTriangle, Check, QrCode, Search, Send, Trash2, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CardContent, CardHeader } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import QRScanner, { QRScannerRef } from '@/components/qr/QRScanner'

type TransmitItem = {
  user_id: string
  identity_id: string
  created_at: string
  updated_at: string
}

type AvailabilityResponse = {
  identity_id: string
  available: boolean
  conflict: 'identity' | 'snapshot' | null
}

type TransmitStatus =
  | 'idle'
  | 'scanning'
  | 'transmitting'
  | 'transmitted'
  | 'error'

const API_BASE = '/api/backend/component_id_transmission'

function formatTimestamp(iso?: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const ComponentIdTransmitter: React.FC = () => {
  const scannerConfig = useMemo(
    () => ({
      aspectRatio: 1,
      fps: 10,
      qrbox: { width: 300, height: 300 },
      rememberLastUsedCamera: true,
      supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
      formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
    }),
    []
  )

  const qrScannerRef = useRef<QRScannerRef | null>(null)
  const elementId = 'id-transmission-reader'
  const cameraContainerId = 'id-transmission-cameracontainer'

  const [pending, setPending] = useState<TransmitItem | null>(null)
  const [isLoadingPending, setIsLoadingPending] = useState(true)

  const [scannedId, setScannedId] = useState('')
  const [inputId, setInputId] = useState('')
  const [isScanning, setIsScanning] = useState(false)

  const [status, setStatus] = useState<TransmitStatus>('idle')
  const [statusMessage, setStatusMessage] = useState<string>('')
  const [isCheckingId, setIsCheckingId] = useState(false)
  const [idAlreadyExists, setIdAlreadyExists] = useState(false)
  const [idCheckMessage, setIdCheckMessage] = useState('')

  const [confirmOverwriteOpen, setConfirmOverwriteOpen] = useState(false)
  const [confirmPayload, setConfirmPayload] = useState<{
    existing: TransmitItem
    newId: string
  } | null>(null)

  // --- Helpers ---------------------------------------------------------------
  const fetchPending = useCallback(async () => {
    setIsLoadingPending(true)
    try {
      const res = await fetch(API_BASE, { cache: 'no-store', credentials: 'include' })
      if (!res.ok) {
        console.error('Failed to fetch pending transmission:', res.status)
        setPending(null)
        return
      }
      const data: { pending: TransmitItem | null } = await res.json()
      setPending(data.pending)
    } catch (err) {
      console.error('Error fetching pending transmission:', err)
      setPending(null)
    } finally {
      setIsLoadingPending(false)
    }
  }, [])

  useEffect(() => {
    fetchPending()
  }, [fetchPending])

  const effectiveId = (scannedId || inputId).trim()

  useEffect(() => {
    if (!effectiveId) {
      setIsCheckingId(false)
      setIdAlreadyExists(false)
      setIdCheckMessage('')
      return
    }

    const controller = new AbortController()
    const timeout = setTimeout(async () => {
      setIsCheckingId(true)
      try {
        const res = await fetch(
          `${API_BASE}/availability/${encodeURIComponent(effectiveId)}`,
          { cache: 'no-store', credentials: 'include', signal: controller.signal },
        )

        if (res.ok) {
          const data = (await res.json()) as AvailabilityResponse
          if (data.available) {
            setIdAlreadyExists(false)
            setIdCheckMessage('Identity id is available for transmission.')
          } else if (data.conflict === 'snapshot') {
            setIdAlreadyExists(true)
            setIdCheckMessage(
              'This UUID is already a snapshot id. Use the physical identity id from the tag.',
            )
          } else {
            setIdAlreadyExists(true)
            setIdCheckMessage(
              'This identity id already exists in the catalog and cannot be transmitted.',
            )
          }
          return
        }

        if (res.status === 400) {
          setIdAlreadyExists(true)
          setIdCheckMessage('Enter a valid identity UUID.')
          return
        }

        // Auth/network edge cases: let POST validate on submit.
        setIdAlreadyExists(false)
        setIdCheckMessage('')
      } catch (err) {
        if ((err as { name?: string })?.name !== 'AbortError') {
          console.error('Error checking ID availability:', err)
          setIdAlreadyExists(false)
          setIdCheckMessage('')
        }
      } finally {
        setIsCheckingId(false)
      }
    }, 250)

    return () => {
      controller.abort()
      clearTimeout(timeout)
    }
  }, [effectiveId])

  const stopScanning = useCallback(async () => {
    if (qrScannerRef.current) {
      await qrScannerRef.current.stopScanning()
    }
    setIsScanning(false)
  }, [])

  const startScanning = useCallback(() => {
    document.getElementById(elementId)?.scrollIntoView()
    if (!isScanning && qrScannerRef.current) {
      setIsScanning(true)
      setStatus('scanning')
      setStatusMessage('Scanning for QR code...')
      qrScannerRef.current.startScanning()
    }
  }, [isScanning])

  const handleScannedCode = useCallback(
    async (decodedText: string) => {
      setScannedId(decodedText.trim())
      setInputId(decodedText.trim())
      setStatus('idle')
      setStatusMessage('')
      await stopScanning()
    },
    [stopScanning]
  )

  const performTransmit = useCallback(
    async (identityId: string, forceOverwrite: boolean) => {
      setStatus('transmitting')
      setStatusMessage('Transmitting...')
      try {
        const res = await fetch(API_BASE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            identity_id: identityId,
            force_overwrite: forceOverwrite,
          }),
        })

        if (res.status === 409) {
          const data: {
            status:
              | 'conflict'
              | 'identity_id_exists'
              | 'snapshot_id_exists'
            existing?: TransmitItem
            new_identity_id?: string
            message?: string
          } = await res.json()

          if (
            data.status === 'identity_id_exists' ||
            data.status === 'snapshot_id_exists'
          ) {
            setStatus('error')
            setStatusMessage(
              data.message || 'This UUID cannot be transmitted as a new identity id.',
            )
            return
          }

          if (data.status === 'conflict' && data.existing && data.new_identity_id) {
            setConfirmPayload({
              existing: data.existing,
              newId: data.new_identity_id,
            })
            setConfirmOverwriteOpen(true)
            setStatus('idle')
            setStatusMessage('')
            return
          }

          setStatus('error')
          setStatusMessage(data.message || 'Transmission conflict.')
          return
        }

        if (!res.ok) {
          const text = await res.text().catch(() => '')
          console.error('Transmit failed:', res.status, text)
          setStatus('error')
          setStatusMessage(`Transmission failed (${res.status}).`)
          return
        }

        const data: {
          status: 'stored' | 'already_pending' | 'overwritten'
          item: TransmitItem
        } = await res.json()

        setPending(data.item)
        setStatus('transmitted')
        setStatusMessage(
          data.status === 'already_pending'
            ? 'This ID was already pending.'
            : data.status === 'overwritten'
            ? 'Pending ID overwritten.'
            : 'ID transmitted.'
        )
      } catch (err) {
        console.error('Error during transmit:', err)
        setStatus('error')
        setStatusMessage('Transmission failed.')
      }
    },
    []
  )

  const handleTransmitClick = useCallback(async () => {
    const id = (scannedId || inputId).trim()
    if (!id) return
    if (idAlreadyExists) {
      setStatus('error')
      setStatusMessage(
        'This identity id already exists in the catalog and cannot be transmitted.',
      )
      return
    }
    await performTransmit(id, false)
  }, [scannedId, inputId, idAlreadyExists, performTransmit])

  const handleConfirmOverwrite = useCallback(async () => {
    if (!confirmPayload) return
    setConfirmOverwriteOpen(false)
    await performTransmit(confirmPayload.newId, true)
    setConfirmPayload(null)
  }, [confirmPayload, performTransmit])

  const handleCancelOverwrite = useCallback(() => {
    setConfirmOverwriteOpen(false)
    setConfirmPayload(null)
  }, [])

  const handleClearPending = useCallback(async () => {
    try {
      const res = await fetch(API_BASE, { method: 'DELETE', credentials: 'include' })
      if (!res.ok) {
        console.error('Failed to clear pending transmission:', res.status)
        return
      }
      setPending(null)
      setStatus('idle')
      setStatusMessage('Pending ID cleared.')
    } catch (err) {
      console.error('Error clearing pending transmission:', err)
    }
  }, [])

  const handleReset = useCallback(async () => {
    if (isScanning) await stopScanning()
    setScannedId('')
    setInputId('')
    setStatus('idle')
    setStatusMessage('')
  }, [isScanning, stopScanning])

  // --- Derived UI state ------------------------------------------------------
  const canTransmit =
    !!effectiveId &&
    !idAlreadyExists &&
    !isCheckingId &&
    status !== 'transmitting' &&
    !isScanning

  const borderClass =
    status === 'transmitted'
      ? 'border-green-500'
      : status === 'error'
      ? 'border-destructive'
      : status === 'scanning' || status === 'transmitting'
      ? 'border-blue-500'
      : 'border-border'

  const statusBadgeClass =
    status === 'transmitted'
      ? 'bg-green-500 text-white'
      : status === 'error'
      ? 'bg-destructive text-destructive-foreground'
      : status === 'scanning' || status === 'transmitting'
      ? 'bg-blue-500 text-white'
      : 'bg-muted text-muted-foreground'

  const placeholderMessage =
    'Camera Feed Placeholder.\n\nScan a QR code to transmit the identity id.'

  return (
    <div className="flex flex-col items-center">
      {/* Current pending ID panel */}
      <div className="w-full max-w-[500px] mb-4">
        <div className="rounded-lg border bg-card/60 p-4 text-sm">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="font-medium mb-1">
                Current pending ID
              </div>
              {isLoadingPending ? (
                <div className="text-muted-foreground">Loading...</div>
              ) : pending ? (
                <div className="space-y-1">
                  <div className="font-mono break-all">
                    {pending.identity_id}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    pending since {formatTimestamp(pending.created_at)}
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground">
                  No pending ID.
                </div>
              )}
            </div>
            {pending && !isLoadingPending && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearPending}
                className="flex-shrink-0"
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Clear
              </Button>
            )}
          </div>
        </div>
      </div>

      <CardHeader className="relative w-full max-w-sm p-1">
        {/* Manual Input */}
        {!isScanning && (
          <div className="flex w-full max-w-sm flex-col gap-2 pb-4">
            <Input
              id="inputFieldTransmitID"
              placeholder="Identity ID (scan or paste)"
              value={inputId}
              onChange={(e) => {
                setInputId(e.target.value)
                setScannedId('')
                if (status !== 'idle') {
                  setStatus('idle')
                  setStatusMessage('')
                }
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleTransmitClick()
                }
              }}
            />
            <Button
              onClick={handleTransmitClick}
              disabled={!canTransmit}
              className="flex items-center gap-2"
            >
              <Send className="h-4 w-4" />
              {isCheckingId
                ? 'Checking ID...'
                : status === 'transmitting'
                ? 'Transmitting...'
                : 'Transmit ID'}
            </Button>
          </div>
        )}

        {/* Scanned / active ID badge */}
        {effectiveId && (
          <div className="w-full grid grid-cols-2 gap-y-3 items-center">
            <div className="flex justify-start min-w-0 w-28">
              <span className="text-sm font-medium text-foreground">
                Active ID:
              </span>
            </div>
            <div className="flex justify-end items-center">
              <Badge
                variant="secondary"
                className={`no-wrap flex-shrink-0 ${statusBadgeClass}`}
              >
                {effectiveId}
              </Badge>
            </div>
          </div>
        )}

        {statusMessage && (
          <div
            className={`mt-2 text-xs ${
              status === 'error'
                ? 'text-destructive'
                : status === 'transmitted'
                ? 'text-green-600 dark:text-green-400'
                : 'text-muted-foreground'
            }`}
          >
            {status === 'transmitted' && (
              <Check className="inline h-3 w-3 mr-1" />
            )}
            {statusMessage}
          </div>
        )}

        {idCheckMessage && status !== 'transmitting' && (
          <div
            className={`mt-2 text-xs ${
              idAlreadyExists
                ? 'text-destructive'
                : 'text-green-600 dark:text-green-400'
            }`}
          >
            {idCheckMessage}
          </div>
        )}
      </CardHeader>

      {/* QR Code Scanner Canvas */}
      <CardContent
        id={cameraContainerId}
        className={`mt-4 p-0 relative w-full max-w-[500px] h-[500px] border-8 rounded-xl ${borderClass} bg-card`}
      >
        <QRScanner
          ref={qrScannerRef}
          elementId={elementId}
          onScanSuccess={handleScannedCode}
          config={scannerConfig}
        />
        {!isScanning && (
          <div className="absolute inset-0 bg-muted/60 flex items-center justify-center text-center rounded">
            <span className="whitespace-pre-wrap text-sm text-muted-foreground px-4">
              {placeholderMessage}
            </span>
          </div>
        )}
      </CardContent>

      <div className="m-4 flex flex-col items-center space-y-3">
        {!isScanning && (
          <Button
            onClick={startScanning}
            variant="outline"
            className="w-[200px] flex items-center gap-2"
          >
            <QrCode className="h-4 w-4" />
            Start QR Code Scan
          </Button>
        )}
        {isScanning && (
          <Button
            onClick={stopScanning}
            variant="outline"
            className="w-[200px]"
          >
            Stop Scanning
          </Button>
        )}
        {!isScanning && effectiveId && (
          <Button
            onClick={handleReset}
            variant="destructive"
            className="w-[200px]"
          >
            <X className="h-4 w-4 mr-1" />
            Reset
          </Button>
        )}
        {!isScanning && !effectiveId && (
          <Button
            variant="outline"
            onClick={handleTransmitClick}
            disabled={!canTransmit}
            className="w-[200px] flex items-center gap-2"
          >
            <Search className="h-4 w-4" />
            Transmit
          </Button>
        )}
      </div>

      {/* Overwrite confirmation dialog */}
      <Dialog
        open={confirmOverwriteOpen}
        onOpenChange={(open) => {
          if (!open) handleCancelOverwrite()
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              Pending ID already exists
            </DialogTitle>
            <DialogDescription>
              You still have a pending identity id in the queue. Do you
              really want to overwrite it?
            </DialogDescription>
          </DialogHeader>

          {confirmPayload && (
            <div className="space-y-3 text-sm">
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">
                  Current pending
                </div>
                <div className="font-mono break-all">
                  {confirmPayload.existing.identity_id}
                </div>
                <div className="text-xs text-muted-foreground">
                  pending since{' '}
                  {formatTimestamp(confirmPayload.existing.created_at)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">
                  New ID
                </div>
                <div className="font-mono break-all">
                  {confirmPayload.newId}
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={handleCancelOverwrite}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleConfirmOverwrite}>
              Overwrite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default ComponentIdTransmitter
