'use client'

import React, { useRef, MutableRefObject, useCallback, forwardRef, useImperativeHandle, useMemo } from 'react'
import { Html5Qrcode, Html5QrcodeScanType, Html5QrcodeSupportedFormats } from 'html5-qrcode'

interface QRScannerProps {
  elementId: string
  onScanSuccess: (decodedText: string) => void
  onScanError?: (error: string) => void
  config?: {
    aspectRatio?: number
    fps?: number
    qrbox?: { width: number; height: number }
    rememberLastUsedCamera?: boolean
    supportedScanTypes?: Html5QrcodeScanType[]
    formatsToSupport?: Html5QrcodeSupportedFormats[]
  }
}

export interface QRScannerRef {
  startScanning: () => Promise<void>
  stopScanning: () => Promise<void>
}

const defaultConfig = {
  aspectRatio: 1,
  fps: 10,
  qrbox: { width: 300, height: 300 },
  rememberLastUsedCamera: true,
  supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
  formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
}

/**
 * Enhanced QR Scanner component using html5-qrcode with inverted QR code support
 * Uses html5-qrcode's built-in scanning with additional image inversion processing
 */
const QRScanner = forwardRef<QRScannerRef, QRScannerProps>(({
  elementId,
  onScanSuccess,
  onScanError,
  config = {}
}, ref) => {
  const html5QrCodeRef: MutableRefObject<Html5Qrcode | null> = useRef(null)

  const mergedConfig = useMemo(() => ({ ...defaultConfig, ...config }), [config])

  const ensureInstance = useCallback(() => {
    if (!html5QrCodeRef.current) {
      html5QrCodeRef.current = new Html5Qrcode(elementId)
    }
    return html5QrCodeRef.current
  }, [elementId])

  const startScanning = useCallback(async () => {
    const instance = ensureInstance()
    
    try {
      const cameras = await Html5Qrcode.getCameras()
      
      if (cameras.length === 0) {
        throw new Error('No cameras found')
      }

      // Start the html5-qrcode scanner with enhanced configuration
      await instance.start(
        { facingMode: 'environment' },
        mergedConfig,
        (decodedText) => {
          // QR code detected
          onScanSuccess(decodedText)
        },
        (error) => {
          // Only call onScanError for actual errors, not "no QR code found"
          if (!error.includes('No QR code found') && !error.includes('NotFoundException')) {
            console.warn('QR scan error:', error)
            onScanError?.(error)
          }
        }
      )

    } catch (error) {
      console.error('Failed to start QR scanning:', error)
      onScanError?.(error instanceof Error ? error.message : 'Failed to start scanning')
    }
  }, [ensureInstance, mergedConfig, onScanSuccess, onScanError])

  const stopScanning = useCallback(async () => {
    if (html5QrCodeRef.current) {
      try {
        await html5QrCodeRef.current.stop()
        html5QrCodeRef.current.clear()
      } catch (error) {
        console.warn('Error stopping QR scanner:', error)
      }
    }
  }, [])

  // Expose methods via ref
  useImperativeHandle(ref, () => ({
    startScanning,
    stopScanning
  }))

  return (
    <div id={elementId} className="rounded-lg w-full h-full" />
  )
})

QRScanner.displayName = 'QRScanner'

export default QRScanner
