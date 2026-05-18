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
  PackagePlus,
  QrCode,
} from 'lucide-react'

import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import QRScanner, { QRScannerRef } from '@/components/qr/QRScanner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
  buildCreateIdentityPayload,
  defaultAddComponentFormState,
  isValidIdentityUuid,
  normalizeScannedIdentityId,
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
    form.lengthMm > 0 &&
    form.widthMm > 0 &&
    form.heightMm > 0

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
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <QrCode className="h-5 w-5" />
              Scan physical tag
            </CardTitle>
            <CardDescription>
              Scan the QR code on the piece to read its identity id. The id must not already exist in
              the catalog.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center space-y-4">
            {!isScanning && (
              <div className="flex w-full max-w-sm flex-col gap-2">
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
              <div className="grid w-full max-w-sm grid-cols-2 items-center gap-y-3">
                <span className="text-sm font-medium text-foreground">Identity ID:</span>
                <div className="flex justify-end">
                  <Badge variant="secondary" className={`flex-shrink-0 ${identityBadgeClass}`}>
                    {effectiveId}
                  </Badge>
                </div>
              </div>
            )}

            {effectiveId && (
              <div
                className={`w-full max-w-sm rounded-md border px-3 py-2 text-sm ${
                  idAvailable === true
                    ? 'border-green-300 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950/40 dark:text-green-100'
                    : idAvailable === false
                      ? 'border-destructive/40 bg-destructive/10 text-destructive'
                      : 'border-border bg-muted/40 text-muted-foreground'
                }`}
              >
                {isCheckingId ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Checking availability…
                  </span>
                ) : (
                  idCheckMessage || 'Enter a valid UUID.'
                )}
              </div>
            )}

            <div
              id={cameraContainerId}
              className={`relative mx-auto mt-2 h-[500px] w-full max-w-[500px] rounded-xl border-8 bg-card p-0 ${identityBorderClass}`}
            >
              <QRScanner
                ref={qrScannerRef}
                elementId={elementId}
                onScanSuccess={handleScannedCode}
                config={scannerConfig}
              />
              {!isScanning && (
                <div className="absolute inset-0 flex items-center justify-center rounded bg-muted/60 text-center">
                  <span className="whitespace-pre-wrap px-4 text-sm text-muted-foreground">
                    {identityPlaceholderMessage}
                  </span>
                </div>
              )}
            </div>

            <div className="flex flex-col items-center space-y-3">
              {!isScanning && (
                <Button
                  type="button"
                  onClick={startScanning}
                  variant="outline"
                  className="flex w-[200px] items-center gap-2"
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

            <div className="flex w-full justify-end pt-2">
              <Button type="button" onClick={goNext} disabled={!canProceedIdentity}>
                Continue
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 'details' && (
        <Card>
          <CardHeader>
            <CardTitle>Metadata & dimensions</CardTitle>
            <CardDescription>
              Enter catalog fields and bounding box size in millimeters (L × W × H). A box
              extrusion is created for the initial snapshot geometry.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="add-name">Name</Label>
                <Input
                  id="add-name"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Component name"
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
              <div className="space-y-2">
                <Label htmlFor="add-material">Material</Label>
                <Input
                  id="add-material"
                  list="add-material-suggestions"
                  value={form.material}
                  onChange={e => setForm(f => ({ ...f, material: e.target.value }))}
                  required
                />
                <datalist id="add-material-suggestions">
                  {materialSuggestions.map(m => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-dataset">Dataset</Label>
                <Input
                  id="add-dataset"
                  list="add-dataset-suggestions"
                  value={form.dataset}
                  onChange={e => setForm(f => ({ ...f, dataset: e.target.value }))}
                  required
                />
                <datalist id="add-dataset-suggestions">
                  {datasetSuggestions.map(d => (
                    <option key={d} value={d} />
                  ))}
                </datalist>
              </div>
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

            <div className="rounded-lg border border-border p-4">
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
                      type="number"
                      min={0.1}
                      step={0.1}
                      value={form[key]}
                      onChange={e =>
                        setForm(f => ({
                          ...f,
                          [key]: parseFloat(e.target.value) || 0,
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
              <div className="space-y-2">
                <Label htmlFor="add-lat">Latitude</Label>
                <Input
                  id="add-lat"
                  type="number"
                  step="any"
                  value={form.lat}
                  onChange={e => setForm(f => ({ ...f, lat: parseFloat(e.target.value) || 0 }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-lon">Longitude</Label>
                <Input
                  id="add-lon"
                  type="number"
                  step="any"
                  value={form.lon}
                  onChange={e => setForm(f => ({ ...f, lon: parseFloat(e.target.value) || 0 }))}
                />
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

            <div className="flex justify-between gap-2">
              <Button type="button" variant="outline" onClick={goBack}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button type="button" onClick={goNext} disabled={!canProceedDetails}>
                Continue
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 'photos' && (
        <Card>
          <CardHeader>
            <CardTitle>Snapshot photos</CardTitle>
            <CardDescription>
              Add photos of the physical piece. Use the camera on site or pick images from your
              device. Photos upload when you finish the wizard.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
          </CardContent>
        </Card>
      )}

      {step === 'finish' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              Review & create
            </CardTitle>
            <CardDescription>
              Confirm the new catalog entry, then create the identity and upload photos.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid gap-2 text-sm">
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Identity id</dt>
                <dd className="font-mono text-xs break-all text-right">{effectiveId}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">Name</dt>
                <dd className="text-right">{form.name.trim() || 'Unnamed Component'}</dd>
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
                  {form.lengthMm.toFixed(1)} × {form.widthMm.toFixed(1)} ×{' '}
                  {form.heightMm.toFixed(1)}
                </dd>
              </div>
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
          </CardContent>
        </Card>
      )}
    </div>
  )
}
