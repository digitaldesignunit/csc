'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Html5QrcodeScanType,
  Html5QrcodeSupportedFormats,
} from 'html5-qrcode'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  MapPin,
  PackagePlus,
  QrCode,
} from 'lucide-react'

import CatalogMetaSelect from '@/components/components/add/CatalogMetaSelect'
import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import QRScanner, { QRScannerRef } from '@/components/qr/QRScanner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { OptionalDateInput } from '@/components/ui/optional-date-input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AddComponentFormState,
  COMPONENT_TYPES,
  CONDITION_VALUES,
  MANUFACTURED_PRECISIONS,
  addComponentDisplayNamePreview,
  buildCreateIdentityPayload,
  defaultAddComponentFormState,
  isValidIdentityUuid,
  normalizeScannedIdentityId,
  parseDimensionMm,
  sanitizeDimensionInput,
} from '@/lib/catalogCreate'
import { uploadSnapshotPhotos } from '@/lib/snapshotPhotos'
import { hexComponentColor } from '@/lib/utils'

const STEPS = ['identity', 'details', 'photos', 'finish'] as const
type Step = (typeof STEPS)[number]

const STEP_LABELS: Record<Step, string> = {
  identity: 'Identity',
  details: 'Details',
  photos: 'Photos',
  finish: 'Finish',
}

const AVAILABILITY_API = '/api/backend/component_id_transmission/availability'
const TRANSMIT_CONSUME_API = '/api/backend/component_id_transmission/consume'

type AvailabilityResponse = {
  identity_id: string
  available: boolean
  conflict: 'identity' | 'snapshot' | null
}

const UNSET = '__unset__'

function hexToRgb(hex: string): [number, number, number] | null {
  const m = hex.trim().replace(/^#/, '')
  if (m.length !== 6) return null
  const r = parseInt(m.slice(0, 2), 16)
  const g = parseInt(m.slice(2, 4), 16)
  const b = parseInt(m.slice(4, 6), 16)
  if ([r, g, b].some(v => Number.isNaN(v))) return null
  return [r, g, b]
}

export default function ComponentAddWizard() {
  const router = useRouter()
  const [step, setStep] = useState<Step>('identity')

  const [identityId, setIdentityId] = useState('')
  const [inputId, setInputId] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [isCheckingId, setIsCheckingId] = useState(false)
  const [idAvailable, setIdAvailable] = useState<boolean | null>(null)
  const [idCheckMessage, setIdCheckMessage] = useState('')

  const [form, setForm] = useState<AddComponentFormState>(defaultAddComponentFormState)
  const [photoFiles, setPhotoFiles] = useState<File[]>([])
  const [materialSuggestions, setMaterialSuggestions] = useState<string[]>([])
  const [datasetSuggestions, setDatasetSuggestions] = useState<string[]>([])

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState<string | null>(null)

  const qrScannerRef = useRef<QRScannerRef | null>(null)
  const elementId = 'add-component-qr-reader'
  const cameraContainerId = 'add-component-cameracontainer'

  const scannerConfig = useMemo(
    () => ({
      aspectRatio: 1,
      fps: 10,
      qrbox: { width: 300, height: 300 },
      rememberLastUsedCamera: true,
      supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
      formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
    }),
    [],
  )

  const effectiveId = normalizeScannedIdentityId(identityId || inputId)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [mRes, dRes] = await Promise.all([
          fetch('/api/backend/identities/meta/materials', { credentials: 'include' }).then(r =>
            r.ok ? r.json() : [],
          ),
          fetch('/api/backend/identities/meta/datasets', { credentials: 'include' }).then(r =>
            r.ok ? r.json() : [],
          ),
        ])
        if (!cancelled) {
          setMaterialSuggestions(Array.isArray(mRes) ? mRes : [])
          setDatasetSuggestions(Array.isArray(dRes) ? dRes : [])
        }
      } catch {
        /* optional suggestions */
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!effectiveId) {
      setIsCheckingId(false)
      setIdAvailable(null)
      setIdCheckMessage('')
      return
    }

    if (!isValidIdentityUuid(effectiveId)) {
      setIsCheckingId(false)
      setIdAvailable(false)
      setIdCheckMessage('Enter a valid identity UUID from the physical tag.')
      return
    }

    const controller = new AbortController()
    const timeout = setTimeout(async () => {
      setIsCheckingId(true)
      try {
        const res = await fetch(`${AVAILABILITY_API}/${encodeURIComponent(effectiveId)}`, {
          cache: 'no-store',
          credentials: 'include',
          signal: controller.signal,
        })

        if (res.ok) {
          const data = (await res.json()) as AvailabilityResponse
          if (data.available) {
            setIdAvailable(true)
            setIdCheckMessage('This identity id is available for a new catalog entry.')
          } else if (data.conflict === 'snapshot') {
            setIdAvailable(false)
            setIdCheckMessage(
              'This UUID is already a snapshot id. Use the physical identity id from the tag.',
            )
          } else {
            setIdAvailable(false)
            setIdCheckMessage('This identity already exists in the catalog.')
          }
          return
        }

        setIdAvailable(false)
        setIdCheckMessage('Could not verify this identity id.')
      } catch (err) {
        if ((err as { name?: string })?.name !== 'AbortError') {
          setIdAvailable(null)
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
    document.getElementById(elementId)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    if (!isScanning && qrScannerRef.current) {
      setIsScanning(true)
      qrScannerRef.current.startScanning()
    }
  }, [isScanning])

  const handleScannedCode = useCallback(
    async (decodedText: string) => {
      const id = normalizeScannedIdentityId(decodedText)
      setIdentityId(id)
      setInputId(id)
      await stopScanning()
    },
    [stopScanning],
  )

  const handleResetIdentity = useCallback(async () => {
    if (isScanning) await stopScanning()
    setIdentityId('')
    setInputId('')
    setIdAvailable(null)
    setIdCheckMessage('')
  }, [isScanning, stopScanning])

  const identityBorderClass =
    isScanning
      ? 'border-blue-500'
      : idAvailable === true
        ? 'border-green-500'
        : idAvailable === false
          ? 'border-destructive'
          : 'border-border'

  const identityBadgeClass =
    idAvailable === true
      ? 'bg-green-500 text-white'
      : idAvailable === false
        ? 'bg-destructive text-destructive-foreground'
        : 'bg-muted text-muted-foreground'

  const identityPlaceholderMessage =
    'Camera Feed Placeholder.\n\nScan the QR code on the physical tag.'

  const canProceedIdentity = Boolean(effectiveId && idAvailable === true && !isCheckingId)

  const canProceedDetails =
    form.material.trim().length > 0 &&
    form.dataset.trim().length > 0 &&
    parseDimensionMm(form.lengthMm) > 0 &&
    parseDimensionMm(form.widthMm) > 0 &&
    parseDimensionMm(form.heightMm) > 0 &&
    form.quantity >= 1

  const stepIndex = STEPS.indexOf(step)

  const goNext = () => {
    const next = STEPS[stepIndex + 1]
    if (next) setStep(next)
  }

  const goBack = () => {
    const prev = STEPS[stepIndex - 1]
    if (prev) setStep(prev)
  }

  const handleSubmit = async () => {
    if (!canProceedIdentity || !canProceedDetails) return

    setSubmitting(true)
    setSubmitError(null)

    try {
      const payload = buildCreateIdentityPayload(effectiveId, form)
      const res = await fetch('/api/backend/identities', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new Error(body || `Create failed (${res.status})`)
      }

      const data = (await res.json()) as {
        identity?: { _id?: string }
        snapshot?: { _id?: string }
      }
      const snapshotId = data.snapshot?._id
      if (!snapshotId) {
        throw new Error('Server did not return a snapshot id.')
      }

      if (photoFiles.length > 0) {
        await uploadSnapshotPhotos(snapshotId, photoFiles)
      }

      await fetch(TRANSMIT_CONSUME_API, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identity_id: effectiveId }),
      }).catch(() => {
        /* optional: clear queued transmission if present */
      })

      router.push(`/components/${effectiveId}`)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create component.')
      setSubmitting(false)
    }
  }

  const colorHex = hexComponentColor([form.colorR, form.colorG, form.colorB])

  const useCurrentLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationError('Geolocation is not supported in this browser.')
      return
    }
    setLocating(true)
    setLocationError(null)
    navigator.geolocation.getCurrentPosition(
      pos => {
        setForm(f => ({
          ...f,
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
        }))
        setLocating(false)
      },
      err => {
        setLocationError(err.message || 'Could not read your location.')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    )
  }, [])

  return (
    <div className="space-y-6">
      <nav aria-label="Add component progress" className="flex flex-wrap gap-2">
        {STEPS.map((s, i) => {
          const done = i < stepIndex
          const active = s === step
          return (
            <Badge
              key={s}
              variant={active ? 'default' : done ? 'secondary' : 'outline'}
              className="px-3 py-1"
            >
              {i + 1}. {STEP_LABELS[s]}
            </Badge>
          )
        })}
      </nav>

      {step === 'identity' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <QrCode className="h-5 w-5" />
              Scan physical tag
            </h2>
            <p className="text-sm text-muted-foreground">
              Scan the QR code on the piece to read its identity id. The id must not already exist in
              the catalog.
            </p>
          </div>
          <div className="flex flex-col items-center">
            <CardHeader className="relative w-full max-w-sm p-1">
              {!isScanning && (
                <div className="flex w-full max-w-sm flex-col gap-2 pb-4">
                  <Label htmlFor="add-identity-id">Or enter identity id manually</Label>
                <Input
                  id="add-identity-id"
                  value={inputId}
                  onChange={e => {
                    setInputId(e.target.value)
                    setIdentityId(e.target.value)
                  }}
                  placeholder="00000000-0000-0000-0000-000000000000"
                  className="font-mono text-sm"
                />
              </div>
            )}

              {effectiveId && (
                <div className="grid w-full grid-cols-2 items-center gap-y-3">
                  <span className="text-sm font-medium text-foreground">Identity ID:</span>
                  <div className="flex justify-end">
                    <Badge variant="secondary" className={`flex-shrink-0 ${identityBadgeClass}`}>
                      {effectiveId}
                    </Badge>
                  </div>
                </div>
              )}

              {effectiveId && (isCheckingId || idCheckMessage) && (
                <div
                  className={`mt-2 text-xs ${
                    idAvailable === false
                      ? 'text-destructive'
                      : idAvailable === true
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-muted-foreground'
                  }`}
                >
                  {isCheckingId ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Checking availability…
                    </span>
                  ) : (
                    idCheckMessage || 'Enter a valid UUID.'
                  )}
                </div>
              )}

            </CardHeader>

            <CardContent
              id={cameraContainerId}
              className={`mt-4 p-0 relative w-full max-w-[500px] h-[500px] border-8 rounded-xl ${identityBorderClass} bg-card`}
            >
              <QRScanner
                ref={qrScannerRef}
                elementId={elementId}
                onScanSuccess={handleScannedCode}
                config={scannerConfig}
              />
              {!isScanning && (
                <div className="absolute inset-0 flex items-center justify-center rounded bg-muted/60 text-center">
                  <span className="whitespace-pre-wrap text-sm text-muted-foreground px-4">
                    {identityPlaceholderMessage}
                  </span>
                </div>
              )}
            </CardContent>

            <div className="m-4 flex flex-col items-center space-y-3">
              {!isScanning && (
                <Button
                  type="button"
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
                  type="button"
                  onClick={() => void stopScanning()}
                  variant="outline"
                  className="w-[200px]"
                >
                  Stop Scanning
                </Button>
              )}
              {!isScanning && effectiveId && (
                <Button
                  type="button"
                  onClick={() => void handleResetIdentity()}
                  variant="destructive"
                  className="w-[200px]"
                >
                  Reset
                </Button>
              )}
            </div>

            <div className="flex w-full max-w-[500px] justify-end">
              <Button type="button" onClick={goNext} disabled={!canProceedIdentity}>
                Continue
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </div>
        </section>
      )}

      {step === 'details' && (
        <section className="space-y-6 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Metadata & dimensions</h2>
            <p className="text-sm text-muted-foreground">
              Enter catalog fields and bounding box size in millimeters (L × W × H). A box
              extrusion is created for the initial snapshot geometry.
            </p>
          </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="add-name">Name (optional)</Label>
                <Input
                  id="add-name"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Leave empty to auto-generate from catalog number"
                />
              </div>
              <div className="space-y-2">
                <Label>Type</Label>
                <Select value={form.type} onValueChange={v => setForm(f => ({ ...f, type: v }))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {COMPONENT_TYPES.map(t => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <CatalogMetaSelect
                id="add-material"
                label="Material"
                value={form.material}
                options={materialSuggestions}
                onChange={material => setForm(f => ({ ...f, material }))}
                customPlaceholder="Custom material"
                required
              />
              <CatalogMetaSelect
                id="add-dataset"
                label="Dataset"
                value={form.dataset}
                options={datasetSuggestions}
                onChange={dataset => setForm(f => ({ ...f, dataset }))}
                customPlaceholder="Custom dataset"
                required
              />
              <div className="space-y-2">
                <Label>Complexity</Label>
                <Select
                  value={String(form.complexity)}
                  onValueChange={v => setForm(f => ({ ...f, complexity: parseInt(v, 10) }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[0, 1, 2, 3].map(c => (
                      <SelectItem key={c} value={String(c)}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-quantity">Quantity</Label>
                <Input
                  id="add-quantity"
                  type="number"
                  min={1}
                  step={1}
                  value={form.quantity}
                  onChange={e =>
                    setForm(f => ({
                      ...f,
                      quantity: Math.max(1, parseInt(e.target.value, 10) || 1),
                    }))
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Identical items counted as one catalog entry (e.g. matching fixtures).
                </p>
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="add-notes">Notes (optional)</Label>
                <Textarea
                  id="add-notes"
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="Site observations, markings, storage location, etc."
                  rows={3}
                  maxLength={5000}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-color">Color (hex)</Label>
                <div className="flex gap-2">
                  <Input
                    id="add-color"
                    type="color"
                    value={colorHex}
                    onChange={e => {
                      const rgb = hexToRgb(e.target.value)
                      if (rgb) {
                        setForm(f => ({
                          ...f,
                          colorR: rgb[0],
                          colorG: rgb[1],
                          colorB: rgb[2],
                        }))
                      }
                    }}
                    className="h-10 w-14 shrink-0 cursor-pointer p-1"
                  />
                  <Input
                    value={colorHex}
                    readOnly
                    className="font-mono text-sm"
                    aria-label="Color hex value"
                  />
                </div>
              </div>
            </div>

            <div>
              <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Bounding box (mm)
              </p>
              <div className="grid grid-cols-3 gap-3">
                {(
                  [
                    ['lengthMm', 'L (length)', 'add-length'],
                    ['widthMm', 'W (width)', 'add-width'],
                    ['heightMm', 'H (height)', 'add-height'],
                  ] as const
                ).map(([key, label, id]) => (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={id}>{label}</Label>
                    <Input
                      id={id}
                      type="text"
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder="mm"
                      value={form[key]}
                      onChange={e =>
                        setForm(f => ({
                          ...f,
                          [key]: sanitizeDimensionInput(e.target.value),
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="add-fragment"
                  checked={form.fragment}
                  onCheckedChange={c => setForm(f => ({ ...f, fragment: c === true }))}
                />
                <Label htmlFor="add-fragment">Fragment</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="add-assembly"
                  checked={form.assembly}
                  onCheckedChange={c => setForm(f => ({ ...f, assembly: c === true }))}
                />
                <Label htmlFor="add-assembly">Assembly</Label>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <Label className="text-sm font-medium">Location</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full sm:w-auto"
                  disabled={locating}
                  onClick={() => useCurrentLocation()}
                >
                  {locating ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <MapPin className="mr-2 h-4 w-4" />
                  )}
                  Use my current location
                </Button>
              </div>
              {locationError && (
                <p className="text-sm text-destructive" role="alert">
                  {locationError}
                </p>
              )}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="add-lat">Latitude</Label>
                  <Input
                    id="add-lat"
                    type="number"
                    step="any"
                    value={form.lat}
                    onChange={e =>
                      setForm(f => ({ ...f, lat: parseFloat(e.target.value) || 0 }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="add-lon">Longitude</Label>
                  <Input
                    id="add-lon"
                    type="number"
                    step="any"
                    value={form.lon}
                    onChange={e =>
                      setForm(f => ({ ...f, lon: parseFloat(e.target.value) || 0 }))
                    }
                  />
                </div>
              </div>
            </div>

            <details className="rounded-lg border border-border/60 p-3">
              <summary className="cursor-pointer text-sm font-medium">Provenance (optional)</summary>
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Condition</Label>
                  <Select
                    value={form.condition === null ? UNSET : String(form.condition)}
                    onValueChange={v =>
                      setForm(f => ({
                        ...f,
                        condition: v === UNSET ? null : parseInt(v, 10),
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Unknown" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={UNSET}>Unknown</SelectItem>
                      {CONDITION_VALUES.map(c => (
                        <SelectItem key={c} value={String(c)}>
                          {c}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Manufactured precision</Label>
                  <Select
                    value={
                      form.manufactured_precision === '' ? UNSET : form.manufactured_precision
                    }
                    onValueChange={v =>
                      setForm(f => ({
                        ...f,
                        manufactured_precision: v === UNSET ? '' : v,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Unknown" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={UNSET}>Unknown</SelectItem>
                      {MANUFACTURED_PRECISIONS.map(p => (
                        <SelectItem key={p} value={p}>
                          {p}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <OptionalDateInput
                  id="add-manufactured-at"
                  label="Manufactured at"
                  value={form.manufactured_at}
                  onChange={manufactured_at => setForm(f => ({ ...f, manufactured_at }))}
                />

                <OptionalDateInput
                  id="add-salvaged-at"
                  label="Salvaged at"
                  value={form.salvaged_at}
                  onChange={salvaged_at => setForm(f => ({ ...f, salvaged_at }))}
                />

                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="add-salvage-source">Salvage source</Label>
                  <Input
                    id="add-salvage-source"
                    value={form.salvage_source}
                    onChange={e => setForm(f => ({ ...f, salvage_source: e.target.value }))}
                    placeholder="e.g. demolition site, building name"
                    maxLength={500}
                  />
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="add-parent">Parent identity id</Label>
                  <Input
                    id="add-parent"
                    value={form.parent_component}
                    onChange={e => setForm(f => ({ ...f, parent_component: e.target.value }))}
                    className="font-mono text-xs"
                    placeholder="Optional UUID"
                  />
                </div>
              </div>
            </details>

          <div className="flex justify-between gap-2 pt-2">
            <Button type="button" variant="outline" onClick={goBack}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
            <Button type="button" onClick={goNext} disabled={!canProceedDetails}>
              Continue
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </section>
      )}

      {step === 'photos' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Snapshot photos</h2>
            <p className="text-sm text-muted-foreground">
              Add photos of the physical piece. Use the camera on site or pick images from your
              device. Photos upload when you finish the wizard.
            </p>
          </div>
            <SnapshotPhotoCapture mode="staged" files={photoFiles} onFilesChange={setPhotoFiles} />
            <div className="flex justify-between gap-2">
              <Button type="button" variant="outline" onClick={goBack}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button type="button" onClick={goNext}>
                Continue
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
        </section>
      )}

      {step === 'finish' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              Review & create
            </h2>
            <p className="text-sm text-muted-foreground">
              Confirm the new catalog entry, then create the identity and upload photos.
            </p>
          </div>
            <dl className="grid gap-2 text-sm">
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Identity id</dt>
                <dd className="font-mono text-xs break-all text-right">{effectiveId}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Name</dt>
                <dd className="text-right">{addComponentDisplayNamePreview(form.name)}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Type / material</dt>
                <dd className="text-right">
                  {form.type} · {form.material}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Dataset</dt>
                <dd className="text-right">{form.dataset}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Dimensions (mm)</dt>
                <dd className="tabular-nums text-right">
                  {parseDimensionMm(form.lengthMm).toFixed(1)} ×{' '}
                  {parseDimensionMm(form.widthMm).toFixed(1)} ×{' '}
                  {parseDimensionMm(form.heightMm).toFixed(1)}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Quantity</dt>
                <dd className="tabular-nums text-right">{form.quantity}</dd>
              </div>
              {form.notes.trim() && (
                <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                  <dt className="shrink-0 text-muted-foreground">Notes</dt>
                  <dd className="max-w-[60%] whitespace-pre-wrap text-right text-xs">
                    {form.notes.trim()}
                  </dd>
                </div>
              )}
              <div className="flex justify-between gap-4 py-1.5">
                <dt className="text-muted-foreground">Photos</dt>
                <dd className="text-right">{photoFiles.length}</dd>
              </div>
            </dl>

            {submitError && (
              <p className="text-sm text-destructive" role="alert">
                {submitError}
              </p>
            )}

            <div className="flex justify-between gap-2">
              <Button type="button" variant="outline" onClick={goBack} disabled={submitting}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button type="button" onClick={handleSubmit} disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating…
                  </>
                ) : (
                  <>
                    <PackagePlus className="mr-2 h-4 w-4" />
                    Create component
                  </>
                )}
              </Button>
            </div>
        </section>
      )}
    </div>
  )
}
