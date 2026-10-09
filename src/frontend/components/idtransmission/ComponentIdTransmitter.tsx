'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Send, Trash2, X } from 'lucide-react'

import UnknownTagLink from '@/components/snapshot/UnknownTagLink'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { formatDay } from '@/lib/utils'
import ScanCamera from '@/components/qr/ScanCamera'
import { type QRScannerRef } from '@/components/qr/QRScanner'

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
  return iso ? formatDay(iso) : ''
}

const ComponentIdTransmitter: React.FC = () => {
  const qrScannerRef = useRef<QRScannerRef | null>(null)

  const [pending, setPending] = useState<TransmitItem | null>(null)
  const [isLoadingPending, setIsLoadingPending] = useState(true)

  const [scannedId, setScannedId] = useState('')
  const [inputId, setInputId] = useState('')
  const [isScanning, setIsScanning] = useState(false)

  const [status, setStatus] = useState<TransmitStatus>('idle')
  const [statusMessage, setStatusMessage] = useState<string>('')
  const [isCheckingId, setIsCheckingId] = useState(false)
  const [idBlocked, setIdBlocked] = useState(false)
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
      setIdBlocked(false)
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
          if (data.conflict === 'snapshot') {
            setIdBlocked(true)
            setIdCheckMessage(
              'This UUID is already a snapshot id. Use the physical identity id from the tag.',
            )
          } else {
            // Existing catalog identities are allowed; uniqueness is
            // enforced by Add Component, not by transmit.
            setIdBlocked(false)
            setIdCheckMessage('')
          }
          return
        }

        if (res.status === 400) {
          setIdBlocked(true)
          setIdCheckMessage('Enter a valid identity UUID.')
          return
        }

        // Auth/network edge cases: let POST validate on submit.
        setIdBlocked(false)
        setIdCheckMessage('')
      } catch (err) {
        if ((err as { name?: string })?.name !== 'AbortError') {
          console.error('Error checking ID availability:', err)
          setIdBlocked(false)
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
    if (idBlocked) {
      setStatus('error')
      setStatusMessage(idCheckMessage || 'This UUID cannot be transmitted.')
      return
    }
    await performTransmit(id, false)
  }, [scannedId, inputId, idBlocked, idCheckMessage, performTransmit])

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
    !idBlocked &&
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

  const placeholderMessage = 'Tap to start the camera and scan the tag to transmit.'

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Current pending ID panel */}
      <div className="w-full max-w-[420px] rounded-lg border bg-card/60 p-3 text-sm">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="mb-1 font-medium">Waiting in the queue</div>
            {isLoadingPending ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : pending ? (
              <div className="space-y-1">
                <div className="break-all font-mono text-xs">{pending.identity_id}</div>
                <div className="text-xs text-muted-foreground">
                  since {formatTimestamp(pending.created_at)}
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground">Nothing is waiting.</div>
            )}
          </div>
          {pending && !isLoadingPending && (
            <Button variant="outline" size="sm" onClick={handleClearPending} className="flex-shrink-0">
              <Trash2 className="mr-1 h-4 w-4" />
              Clear
            </Button>
          )}
        </div>
      </div>

      <ScanCamera
        scannerRef={qrScannerRef}
        elementId="id-transmission-reader"
        onScanSuccess={handleScannedCode}
        isScanning={isScanning}
        onStart={startScanning}
        onStop={() => void stopScanning()}
        borderClass={borderClass}
        message={placeholderMessage}
      >
        {!isScanning && effectiveId && (
          <Button variant="ghost" size="sm" onClick={handleReset} className="gap-1.5">
            <X className="h-4 w-4" aria-hidden />
            Clear the id
          </Button>
        )}
      </ScanCamera>

      <div className="flex w-full max-w-[420px] gap-2">
        <Input
          id="inputFieldTransmitID"
          aria-label="Identity id"
          placeholder="or paste the identity id"
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
            if (e.key === 'Enter') handleTransmitClick()
          }}
        />
        <Button onClick={handleTransmitClick} disabled={!canTransmit} className="gap-1.5">
          <Send className="h-4 w-4" aria-hidden />
          {isCheckingId ? 'Checking...' : status === 'transmitting' ? 'Sending...' : 'Transmit'}
        </Button>
      </div>

      {effectiveId && (
        <p className="w-full max-w-[420px] break-all text-center font-mono text-xs text-muted-foreground">
          {effectiveId}
        </p>
      )}

      {statusMessage && (
        <div
          role="status"
          className={`text-xs ${
            status === 'error'
              ? 'text-destructive'
              : status === 'transmitted'
                ? 'text-green-600 dark:text-green-400'
                : 'text-muted-foreground'
          }`}
        >
          {status === 'transmitted' && <Check className="mr-1 inline h-3 w-3" />}
          {statusMessage}
        </div>
      )}

      {idCheckMessage && status !== 'transmitting' && (
        <div className={`text-xs ${idBlocked ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}>
          {idCheckMessage}
        </div>
      )}
      <UnknownTagLink id={effectiveId} className="text-xs text-muted-foreground" />

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
