'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import { resolveStatic } from '@/lib/utils'
import { Terminal, BookOpen, Code, Database, Settings, HelpCircle, ChevronRight, ChevronDown, FileImage, Download, Check, FileText, ArrowRight, WandSparkles, Sparkles, Box, Construction } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { toast } from 'sonner'

type GHInterfacePageClientProps = {
  ghInterfaceDeactivated: boolean
}

export default function GHInterfacePageClient({ ghInterfaceDeactivated }: GHInterfacePageClientProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['getting-started']))
  const [releaseVersion, setReleaseVersion] = useState<string>('')
  const [isDownloading, setIsDownloading] = useState<boolean>(false)
  const [updateCopied, setUpdateCopied] = useState<boolean>(false)

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sectionId)) {
        newSet.delete(sectionId)
      } else {
        newSet.add(sectionId)
      }
      return newSet
    })
  }

  useEffect(() => {
    if (ghInterfaceDeactivated) return

    const fetchVersion = async () => {
      try {
        const response = await fetch('/api/backend/ghinterface/version')
        if (response.ok) {
          const data = await response.json()
          setReleaseVersion(data.version || '')
        }
      } catch (error) {
        console.error('Failed to fetch release version:', error)
      }
    }
    
    fetchVersion()
  }, [ghInterfaceDeactivated])

  const handleDownload = async () => {
    setIsDownloading(true)
    try {
      const response = await fetch('/api/backend/ghinterface/download')
      if (response.ok) {
        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('content-disposition')
        const filename = contentDisposition 
          ? contentDisposition.split('filename=')[1]?.replace(/"/g, '')
          : 'csc-grasshopper-interface.zip'
        
        // Create blob and download
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      } else {
        console.error('Download failed:', response.statusText)
      }
    } catch (error) {
      console.error('Download error:', error)
    } finally {
      setIsDownloading(false)
    }
  }

  const ComponentCard = ({ 
    icon: Icon, 
    name, 
    description, 
    inputs, 
    outputs, 
    tip,
    imagePath
  }: {
    icon: React.ComponentType<{ className?: string }>
    name: string
    description: string
    inputs: Array<{label: string, description: string}>
    outputs: Array<{label: string, description: string}>
    tip?: string
    imagePath?: string
  }) => {
    const [isCopying, setIsCopying] = useState<boolean>(false)
    const [copied, setCopied] = useState<boolean>(false)

    const handleCopyXml = async () => {
      setIsCopying(true)
      try {
        const xmlName = `DDU_${name}`
        const res = await fetch(`/api/backend/ghinterface/xml/${encodeURIComponent(xmlName)}`)
        if (!res.ok) {
          console.error('Failed to fetch XML:', res.status)
          toast.error('XML not available for this component.')
          return
        }
        const xmlText = await res.text()
        await navigator.clipboard.writeText(xmlText)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch (err) {
        console.error('Copy XML error:', err)
        toast.error('Copy to clipboard failed.')
      } finally {
        setIsCopying(false)
      }
    }

    return (
    <div className="border rounded-lg p-4 bg-white/60 dark:bg-gray-900" data-component-card={name}>
      <div className="w-full h-110 bg-white rounded-lg flex items-center justify-center border-2 border-dashed border-muted-foreground/25 mb-4 overflow-hidden">
        {imagePath ? (
          <Image
            src={imagePath}
            alt={`${name} component screenshot`}
            width={800}
            height={500}
            className="w-full h-full object-contain sm:object-cover"
            unoptimized={true}
            priority={false}
          />
        ) : (
          <div className="text-center text-muted-foreground">
            <FileImage className="h-12 w-12 mx-auto mb-3" />
            <p className="text-lg font-medium">{name}</p>
            <p className="text-sm">Component Screenshot</p>
          </div>
        )}
      </div>
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-3">
          <h4 className="font-semibold text-lg flex items-center gap-2">
            <Icon className="h-5 w-5" />
            {name}
          </h4>
          <span className="hidden sm:block sm:flex-1" />
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyXml}
                  disabled={isCopying}
                  className="h-8 px-3 flex-shrink-0 w-fit"
                >
                  {copied ? (
                    <>
                      <Check className="h-4 w-4 mr-2 text-green-600" />
                      <span>Copied! Paste into GH!</span>
                    </>
                  ) : (
                    <>
                      <FileText className="h-4 w-4 mr-2" />
                      <span>Copy GH XML</span>
                    </>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <div className="text-center text-sm">
                  {copied ? 'Copied! Paste into GH!' : 'Copy Grasshopper Component to Clipboard'}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <p className="text-muted-foreground mb-3">
          {description}
        </p>
        <div className="space-y-3">
          <div>
            <h5 className="font-medium text-sm mb-1">Inputs:</h5>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              {inputs.map((input, index) => (
                <li key={index}>
                  • <strong>{input.label}:</strong> {input.description.split('\n').map((line, lineIndex) => (
                    <span key={lineIndex}>
                      {lineIndex > 0 && <br />}
                      {line}
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h5 className="font-medium text-sm mb-1">Outputs:</h5>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              {outputs.map((output, index) => (
                <li key={index}>
                  • <strong>{output.label}:</strong> {output.description.split('\n').map((line, lineIndex) => (
                    <span key={lineIndex}>
                      {lineIndex > 0 && <br />}
                      {line}
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
          {tip && (
            <div className="bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded p-3">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                <strong>Tip:</strong> {tip.split('\n').map((line, lineIndex) => (
                  <span key={lineIndex}>
                    {lineIndex > 0 && <br />}
                    {line}
                  </span>
                ))}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )}

  const sections = [
    {
      id: 'getting-started',
      title: 'Getting Started',
      icon: BookOpen,
      content: (
        <div className="space-y-6 pt-2" >
          {ghInterfaceDeactivated ? (
            <div className="bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-800 rounded-lg p-4">
              <h4 className="font-semibold text-orange-900 dark:text-orange-100 mb-2 flex items-center gap-2">
                <Construction className="h-4 w-4" />
                Currently Updating
              </h4>
              <p className="text-sm text-orange-800 dark:text-orange-200">
                The CSC Grasshopper Interface is currently being updated. Downloads and automatic updates are temporarily unavailable. Please check back soon.
              </p>
            </div>
          ) : (
            <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
              <h4 className="font-semibold text-green-900 dark:text-green-100 mb-2 flex items-center gap-2">
                <Download className="h-4 w-4" />
                Download Grasshopper Interface
              </h4>
              <p className="text-sm text-green-800 dark:text-green-200 mb-3">
                Download the complete Grasshopper interface with all user objects and example files.
                {releaseVersion && (
                  <span className="block mt-1 font-medium">
                    Latest version: {releaseVersion}
                  </span>
                )}
              </p>
              <div className="flex gap-3">
                <button 
                  onClick={handleDownload}
                  disabled={isDownloading}
                  className="bg-green-600 hover:bg-green-700 disabled:bg-green-400 disabled:cursor-not-allowed text-white px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer"
                >
                  {isDownloading ? 'Downloading...' : `Download Interface ${releaseVersion ? `(${releaseVersion})` : '(.zip)'}`}
                </button>
              </div>
            </div>
          )}

          <p className="text-muted-foreground">
            The DDU CSC Grasshopper Interface provides components for working with the Catalog of Second Chances. This tutorial covers each component and their usage.
          </p>

          <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
            <h4 className="font-semibold text-amber-900 dark:text-amber-100 mb-2">Identity &amp; Snapshot Model</h4>
            <p className="text-sm text-amber-800 dark:text-amber-200 mb-2">
              Catalog entries are split into a stable <strong>identity</strong> and one or more versioned <strong>snapshots</strong>.
            </p>
            <ul className="text-sm text-amber-800 dark:text-amber-200 space-y-1">
              <li>• <strong>Identity</strong> — stable catalog entry: type, material, dataset, provenance (manufactured/salvaged dates, parent identities), and attributes.</li>
              <li>• <strong>Snapshot</strong> — versioned state: geometry, descriptors, condition, placement frame (iframe), PCA frame, color, location, and notes.</li>
              <li>• <strong>Compose JSON</strong> — most components pass data as <code className="text-xs">{`{identity, snapshots[]}`}</code> pairs. Use <strong>CSC_DisassembleComponent</strong> to unpack them in Grasshopper.</li>
              <li>• <strong>Designs</strong> pin specific snapshot versions (not identity/current) and store placement iframes per snapshot.</li>
            </ul>
          </div>

          {!ghInterfaceDeactivated && (
            <div className="bg-purple-50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
              <h4 className="font-semibold text-purple-900 dark:text-purple-100 mb-2 flex items-center gap-2">
                <FileText className="h-4 w-4" />
                NEW! Automatic Updater
              </h4>
              <p className="text-sm text-purple-800 dark:text-purple-200 mb-3">
                Make your life easier and keep your CSC Grasshopper components up-to-date without headache! Use the new <strong>CSC_Update</strong> component to check for and install updates from the server.
              </p>
              <div className="flex items-center gap-3">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => {
                    if (!expandedSections.has('authentication')) {
                      toggleSection('authentication')
                    }
                    setTimeout(() => {
                      const updateCard = document.querySelector('[data-component-card="CSC_Update"]')
                      if (updateCard) {
                        updateCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
                      } else {
                        const sectionElement = document.querySelector('[data-section-id="authentication"]')
                        if (sectionElement) {
                          sectionElement.scrollIntoView({ behavior: 'smooth', block: 'start' })
                        }
                      }
                    }, 200)
                  }}
                  className="h-7 px-3 bg-purple-600 hover:bg-purple-700 text-white"
                >
                  <span className="text-xs">Find out more</span>
                  <ArrowRight className="h-3 w-3 ml-1" />
                </Button>
              </div>

              <div className="mt-3">
                <p className="text-sm text-purple-800 dark:text-purple-200 mb-3">
                  <strong>Also NEW:</strong> Copy CSC Grasshopper Components to your clipboard and paste into Grasshopper.<br />
                  It&apos;s like <span className="inline-flex items-center"><Sparkles className="h-3 w-3" /></span> magic <span className="inline-flex items-center"><WandSparkles className="h-3 w-3" /></span>!
                  Give it a try with the <strong>CSC_Update</strong> component below.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={async () => {
                          try {
                            const xmlName = 'DDU_CSC_Update'
                            const res = await fetch(`/api/backend/ghinterface/xml/${encodeURIComponent(xmlName)}`)
                            if (!res.ok) {
                              console.error('Failed to fetch XML:', res.status)
                              return
                            }
                            const xmlText = await res.text()
                            await navigator.clipboard.writeText(xmlText)
                            setUpdateCopied(true)
                            setTimeout(() => setUpdateCopied(false), 2000)
                          } catch (err) {
                            console.error('Copy error:', err)
                          }
                        }}
                        className="h-7 px-2"
                      >
                        {updateCopied ? (
                          <>
                            <Check className="h-3 w-3 mr-1 text-green-600" />
                            <span className="text-xs">Copied! Paste into GH!</span>
                          </>
                        ) : (
                          <>
                            <FileText className="h-3 w-3 mr-1" />
                            <span className="text-xs">Copy GH Component XML</span>
                          </>
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <div className="text-center text-xs">
                        {updateCopied ? 'Copied! Paste into GH!' : 'Copy Grasshopper Component to Clipboard'}
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>
          )}

          <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <h4 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">Prerequisites</h4>
            <ul className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
              <li>• Rhino 8 or later with Grasshopper installed</li>
              <li>• DDU CSC user account (register at the main website)</li>
              <li>• Basic understanding of Grasshopper workflows</li>
              <li>• Internet connection for API access</li>
            </ul>
          </div>
        </div>
      )
    },
    {
      id: 'authentication',
      title: 'Session Components',
      icon: Settings,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Terminal}
            name="CSC_Session"
            description="Handles user authentication with the remote API, manages access tokens, and provides caching functionality for API responses and geometry. Stores authentication state in scriptcontext.sticky."
            inputs={[
              { label: 'Username', description: 'Your Username or E-Mail' },
              { label: 'Password', description: 'Your password' },
              { label: 'Refresh', description: 'Refresh toggle, press when your token expired' },
              { label: 'DisableCache', description: 'Disable caching (default: False - caching enabled)' },
              { label: 'ClearCache', description: 'Clear cache (default: False)' }
            ]}
            outputs={[
              { label: 'Status', description: 'Authentication status and cache info' }
            ]}
            tip="Automatically caches authentication and component data locally for faster access."
            imagePath={resolveStatic('/gh-interface/csc_session.jpg')}
          />

          {!ghInterfaceDeactivated && (
            <ComponentCard
              icon={Settings}
              name="CSC_Update"
              description="Updates component sources and userobjects in document from server. Checks for available updates and installs them automatically. NOTE: CheckForUpdates must be True to check for updates AND to install updates! Switch on both to update everything."
              inputs={[
                { label: 'CheckForUpdates', description: 'Toggle to check for updates on the server' },
                { label: 'InstallUpdates', description: 'Toggle to install updates from server' }
              ]}
              outputs={[
                { label: 'Status', description: 'Update status and information about installed updates' }
              ]}
              tip="Keep your CSC Grasshopper components up-to-date without headache! Run this component periodically to get the latest versions of all Grasshopper components from the server."
              imagePath={resolveStatic('/gh-interface/csc_update.jpg')}
            />
          )}
        </div>
      )
    },
    {
      id: 'Catalog-interface',
      title: 'Catalog Interface Components',
      icon: Database,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Database}
            name="CSC_ListIdentitySnapshots"
            description="Lists all snapshot versions for one identity (id and name). Input can be an identity UUID or compose JSON."
            inputs={[
              { label: 'Input', description: 'Identity UUID or compose JSON ({identity, snapshots[]})' },
            ]}
            outputs={[
              { label: 'SnapshotID', description: 'Snapshot UUIDs ordered by version' },
              { label: 'SnapshotName', description: 'Snapshot names (parallel to SnapshotID)' },
            ]}
            tip="Uses GET /identities/{id}/snapshots. Pair with FetchComposeSnapshot to load a specific version."
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchComposeAllSnapshots"
            description="Fetches compose JSON with every snapshot version for one identity ({identity, snapshots[]})."
            inputs={[
              { label: 'Input', description: 'Identity UUID or compose JSON ({identity, snapshots[]})' },
            ]}
            outputs={[
              { label: 'ComposeJSON', description: 'Full multi-version compose from GET /identities/{id}/compose?snapshots=all' },
            ]}
            tip="Use with ComposeToD2P (SnapshotScope=all) to build D2P members for every version."
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchComposeSnapshot"
            description="Fetches compose JSON for one identity and a specific snapshot ({identity, snapshots:[one]})."
            inputs={[
              { label: 'Input', description: 'Identity UUID or compose JSON ({identity, snapshots[]})' },
              { label: 'SnapshotID', description: 'Snapshot UUID to fetch' },
            ]}
            outputs={[
              { label: 'ComposeJSON', description: 'Compose with the requested snapshot only (snapshots length 1)' },
            ]}
            tip="Uses GET /identities/{id}/compose?snapshots=<uuid>. Current-snapshot-only fetch remains CSC_FetchComponents."
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchComponents"
            description="Fetches specific identities (with their current snapshot) from the remote Catalog by their identity IDs. Supports caching and returns compose JSON ({identity, snapshots:[current]}) with error handling for missing identities."
            inputs={[
              { label: 'ComponentID', description: 'One or many identity IDs (UUIDs) to fetch' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'Compose JSON per entry ({identity, snapshots[]}) fetched from the server. Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="Supports ETag caching for faster subsequent access. Handles missing identities gracefully."
            imagePath={resolveStatic('/gh-interface/csc_fetchcomponents.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchAllComponents"
            description="Fetches all available components from the remote Catalog API with caching support. Returns all components as a list of JSON strings."
            inputs={[
              { label: 'None', description: 'This component has no inputs' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'The ComponentData that was fetched from the server as JSON. Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="Use with caution for large datasets. Supports caching for better performance on subsequent calls."
            imagePath={resolveStatic('/gh-interface/csc_fetchallcomponents.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FilterComponents"
            description="Filters a list of compose JSON entries ({identity, snapshots[]}) based on various criteria (type, material, dataset, complexity, fragment, bounding box dimensions). Works with local compose data from fetch components."
            inputs={[
              { label: 'Type', description: 'Component type filter (identity.type, e.g., "beam", "slab", "column")' },
              { label: 'Material', description: 'Material type filter (identity.material, e.g., "concrete", "steel", "wood")' },
              { label: 'Dataset', description: 'Dataset name filter (identity.dataset, e.g., "sas_cita_scans", "mineral_composite_sheets")' },
              { label: 'Complexity', description: 'Complexity level filter (snapshot.complexity, 0-3, where 0=simple, 3=complex)' },
              { label: 'Fragment', description: 'Fragment status filter (snapshot.fragment, True for fragments, False for complete)' },
              { label: "MinDimensionX", description: "Minimum X dimension filter (snapshot.bbx)" },
              { label: "MaxDimensionX", description: "Maximum X dimension filter (snapshot.bbx)" },
              { label: "MinDimensionY", description: "Minimum Y dimension filter (snapshot.bbx)" },
              { label: "MaxDimensionY", description: "Maximum Y dimension filter (snapshot.bbx)" },
              { label: "MinDimensionZ", description: "Minimum Z dimension filter (snapshot.bbx)" },
              { label: "MaxDimensionZ", description: "Maximum Z dimension filter (snapshot.bbx)" },
              { label: 'ComponentData', description: 'Compose JSON strings to filter ({identity, snapshots[]}), e.g. from FetchAllComponents, FetchComponents, or FetchFilteredComponents' },
            ]}
            outputs={[
              { label: 'FilterDescription', description: 'Human-readable description of the applied filters' },
              { label: 'FilteredComponentData', description: 'Filtered compose JSON strings ({identity, snapshots[]}). Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="Local filter for compose data. Use after FetchAllComponents, FetchComponents, or FetchFilteredComponents to narrow results without another API call."
            imagePath={resolveStatic('/gh-interface/csc_filtercomponents.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchFilteredComponents"
            description="Fetches identities (with their current snapshot) from the remote Catalog based on filter criteria (type, material, dataset, complexity, fragment, bounding box dimensions). Mirrors the web catalog filter menu and returns compose JSON ({identity, snapshots[]}) results."
            inputs={[
              { label: 'Type', description: 'Component type filter (e.g., "beam", "slab", "column")' },
              { label: 'Material', description: 'Material type filter (e.g., "concrete", "steel", "wood")' },
              { label: 'Dataset', description: 'Dataset name filter (e.g., "sas_cita_scans", "mineral_composite_sheets")' },
              { label: 'Complexity', description: 'Complexity level filter (0-3, where 0=simple, 3=complex)' },
              { label: 'Fragment', description: 'Fragment status filter (True for fragments, False for complete)' },
              { label: 'MinDimensionX', description: 'Minimum X dimension filter (bounding box)' },
              { label: 'MaxDimensionX', description: 'Maximum X dimension filter (bounding box)' },
              { label: 'MinDimensionY', description: 'Minimum Y dimension filter (bounding box)' },
              { label: 'MaxDimensionY', description: 'Maximum Y dimension filter (bounding box)' },
              { label: 'MinDimensionZ', description: 'Minimum Z dimension filter (bounding box)' },
              { label: 'MaxDimensionZ', description: 'Maximum Z dimension filter (bounding box)' },
              { label: 'ReservedStatus', description: 'Reservation status filter: -1=ignore, 0=not reserved, 1=reserved by current user' }
            ]}
            outputs={[
              { label: 'FilterDescription', description: 'Human-readable description of the applied filters and query' },
              { label: 'ComponentData', description: 'Compose JSON per entry ({identity, snapshots[]}) fetched from the server. Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="Filters mirror the web catalog filter menu (plus a reservation-status filter) and run server-side on validated current snapshots. More efficient than fetching all components and filtering locally."
            imagePath={resolveStatic('/gh-interface/csc_fetchfilteredcomponents.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchReducedGeometry"
            description="Fetches the reduced (catalog default) snapshot geometry as binary PLY from the API or local cache, parses it to Rhino meshes and point clouds, and applies the snapshot iframe transform."
            inputs={[
              { label: 'Input', description: 'Input can be:\na) Geometry with the \'csc_component\' compose userstring\nb) A compose JSON string ({identity, snapshots[]})\nc) A raw identity_id (resolves current snapshot)\nd) A raw snapshot_id' }
            ]}
            outputs={[
              { label: 'GeometryData', description: 'Fetched reduced geometry as Rhino meshes and point clouds (one object per snapshot primitive)' },
              { label: 'GeometrySource', description: 'Per-primitive source: reduced (mesh PLY) or primitive (inline fallback, including point-cloud previews)' },
              { label: 'SnapshotID', description: 'Snapshot ID that was processed' }
            ]}
            tip="Meshes fall back to the inline primitive when no reduced PLY is available. Point clouds have no reduced PLY — the inline preview (at most 5000 points) is returned instead."
            imagePath={resolveStatic('/gh-interface/csc_fetchgeometry.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchDetailedGeometry"
            description="Fetches the detailed (high fidelity) snapshot geometry as binary PLY from the API or local cache, parses it to Rhino meshes and point clouds, and applies the snapshot iframe transform."
            inputs={[
              { label: 'Input', description: 'Input can be:\na) Geometry with the \'csc_component\' compose userstring\nb) A compose JSON string ({identity, snapshots[]})\nc) A raw identity_id (resolves current snapshot)\nd) A raw snapshot_id' }
            ]}
            outputs={[
              { label: 'GeometryData', description: 'Fetched detailed geometry as Rhino meshes and point clouds (one object per snapshot primitive)' },
              { label: 'GeometrySource', description: 'Per-primitive source: detailed/reduced (mesh PLY), detailed (point-cloud PLY), or primitive (inline fallback)' },
              { label: 'SnapshotID', description: 'Snapshot ID that was processed' }
            ]}
            tip="Meshes fall back to reduced PLY, then inline primitives, when no detailed PLY is available. Point clouds prefer the full PLY, then the inline preview."
            imagePath={resolveStatic('/gh-interface/csc_fetchgeometry.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchDesign"
            description="Fetches a design from the remote Catalog along with all pinned snapshot placements. Resolves each snapshot reference to compose JSON ({identity, snapshots[]}) and overwrites snapshot.iframe with the design insertion frame. Uses caching for optimal performance."
            inputs={[
              { label: 'DesignID', description: 'Design ID to fetch' }
            ]}
            outputs={[
              { label: 'DesignData', description: 'Design JSON string' },
              { label: 'ComponentData', description: 'Compose JSON per placement with design iframe applied' },
              { label: 'AdditionalGeometryData', description: 'Additional geometry items (list of JSON strings)' },
              { label: 'AdditionalGeometry', description: 'Additional geometry as Rhino meshes' }
            ]}
            tip="Designs pin specific snapshot versions, not identity/current. Use DisassembleComponent on ComponentData outputs."
            imagePath={resolveStatic('/gh-interface/csc_fetchdesign.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchTransmittedID"
            description="Fetches the currently pending transmitted identity ID for the signed-in user. Used with the web Scan & Identify / Transmit ID workflow: after scanning a physical tag in the browser, the pending ID can be picked up here and fed into CreateComponentIdentity."
            inputs={[
              { label: 'Refresh', description: 'Toggle to fetch the latest pending transmitted ID from the server' }
            ]}
            outputs={[
              { label: 'ComponentID', description: 'Pending identity UUID transmitted from the web interface. Empty when none is pending.' }
            ]}
            tip="AddComponentIdentity automatically consumes the pending transmitted ID after a successful create. FetchTransmittedID is useful for previewing or wiring the ID into CreateComponentIdentity before posting."
          />
        </div>
      )
    },
    {
      id: 'component-operations',
      title: 'Component Operations',
      icon: Code,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Code}
            name="CSC_CreateComponentIdentity"
            description="Builds a CreateComponentRequest JSON payload from Rhino geometry for POST /identities. Creates the initial identity together with its version-0 snapshot. Computes PCA orientation, mesh reduction, and stages binary PLY files under pending_identity_assets/{identity_id}/."
            inputs={[
              { label: 'ClearLocalStorage', description: 'If True, clears pending_identity_assets staging (does not affect Session API cache)' },
              { label: 'IdentityID', description: 'Identity UUID from physical tag or FetchTransmittedID (must be a valid UUID)' },
              { label: 'Name', description: 'Display name for the initial snapshot (e.g. My Beam 01)' },
              { label: 'Type', description: 'Component type (e.g., "panel", "rubble"). Must match the backend component type enum.' },
              { label: 'Material', description: 'Material type (e.g., "steel", "concrete", "wood")' },
              { label: 'Dataset', description: 'Dataset this identity belongs to (e.g. my_rubble_dataset)' },
              { label: 'Complexity', description: 'Complexity level (0=simple, 1=normal, 2=complex, 3=very complex)' },
              { label: 'Fragment', description: 'Fragment status (True for fragments, False for complete)' },
              { label: 'Assembly', description: 'Assembly status (True for assemblies, False for individual)' },
              { label: 'Color', description: 'Snapshot color (System.Drawing.Color)' },
              { label: 'Location', description: 'Location as Vector3d (X=latitude, Y=longitude, Z ignored)' },
              { label: 'Geometry', description: 'Rhino geometry — single Mesh or Extrusion, or a list of Meshes' },
              { label: 'MarkerPoints', description: 'Marker points as list of Point3d for identification and positioning' },
              { label: 'Condition', description: 'Optional condition grade (0=destroyed/retired, 1=poor, 2=average, 3=good). Leave unconnected for unknown.' },
              { label: 'ManufacturedAt', description: 'Optional ISO-8601 UTC manufacturing timestamp' },
              { label: 'ManufacturedPrecision', description: 'Optional precision qualifier: exact, month, year, or unknown' },
              { label: 'SalvageSource', description: 'Optional salvage source text (e.g. building name)' },
              { label: 'SalvagedAt', description: 'Optional ISO-8601 UTC salvage timestamp' },
              { label: 'ParentIdentity', description: 'Optional parent identity UUID (lineage after split/merge)' },
              { label: 'Notes', description: 'Optional free-text notes for the initial snapshot (max 5000)' },
              { label: 'Quantity', description: 'Count of identical physical items (integer ≥ 1, default 1)' },
              { label: 'Reinforcements', description: 'Optional reinforcement JSON strings from CreateReinforcement (one or many; merged into geometry.reinforcements)' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'CreateComponentRequest JSON for POST /identities (inline geometry + staged PLY manifest)' }
            ]}
            tip="Pair with CSC_AddComponentIdentity to post. Wire CreateReinforcement → Reinforcements for inline rebar centerlines. Use CSC_FetchTransmittedID to obtain the identity UUID after a web tag scan."
            imagePath={resolveStatic('/gh-interface/csc_createcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_AddComponentIdentity"
            description="Creates a new catalog identity and its version-0 snapshot via POST /identities. Accepts CreateComponentRequest JSON from CreateComponentIdentity, uploads staged binary PLY mesh files, and optionally consumes a pending transmitted ID after success."
            inputs={[
              { label: 'ComponentData', description: 'CreateComponentRequest JSON from CreateComponentIdentity' },
              { label: 'Run', description: 'Toggle to execute the create operation' }
            ]}
            outputs={[
              { label: 'AddedComponentData', description: 'Compose response JSON ({identity, snapshots[]}) returned from POST /identities' }
            ]}
            tip="Validates the payload, posts the identity, uploads staged PLY files, and non-fatally consumes any pending transmitted ID. Requires authentication."
            imagePath={resolveStatic('/gh-interface/csc_addcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_CreateComponentSnapshot"
            description="Builds a CreateSnapshotRequest JSON payload from Rhino geometry for an existing identity (POST /identities/{id}/snapshots). Computes PCA orientation, mesh reduction, and stages binary PLY files under pending_snapshot_assets/{snapshot_id}/."
            inputs={[
              { label: 'ClearLocalStorage', description: 'If True, clears pending_snapshot_assets staging (does not affect Session API cache)' },
              { label: 'IdentityID', description: 'Existing identity UUID to attach the new snapshot to' },
              { label: 'SnapshotID', description: 'New snapshot UUID (optional; auto-generated when empty)' },
              { label: 'Name', description: 'Snapshot display name (optional; inherits current name when empty)' },
              { label: 'Complexity', description: 'Complexity level (0=simple, 1=normal, 2=complex, 3=very complex)' },
              { label: 'Fragment', description: 'Fragment status (True for fragments, False for complete)' },
              { label: 'Assembly', description: 'Assembly status (True for assemblies, False for individual)' },
              { label: 'Color', description: 'Snapshot color (System.Drawing.Color)' },
              { label: 'Location', description: 'Location as Vector3d (X=latitude, Y=longitude, Z ignored)' },
              { label: 'Geometry', description: 'Rhino geometry — single Mesh or Extrusion, or a list of Meshes' },
              { label: 'MarkerPoints', description: 'Marker points as list of Point3d' },
              { label: 'Condition', description: 'Optional condition grade (0–3). Leave unconnected for unknown.' },
              { label: 'Notes', description: 'Optional free-text notes for the new snapshot (max 5000)' },
              { label: 'Quantity', description: 'Count of identical physical items (integer ≥ 1, default 1)' },
              { label: 'Virtual', description: 'Virtual snapshot flag (True = proposal/hypothetical state, not yet validated)' },
              { label: 'Reinforcements', description: 'Optional reinforcement JSON strings from CreateReinforcement (one or many; merged into geometry.reinforcements)' }
            ]}
            outputs={[
              { label: 'SnapshotData', description: 'CreateSnapshotRequest JSON (includes identity_id) for POST /identities/{id}/snapshots' }
            ]}
            tip="Use when an identity already exists and you need a new version — e.g. after re-scanning, condition change, or geometry update. Wire CreateReinforcement → Reinforcements for inline rebar centerlines."
            imagePath={resolveStatic('/gh-interface/csc_createcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_AddComponentSnapshot"
            description="Creates a new snapshot for an existing identity via POST /identities/{id}/snapshots. Accepts CreateSnapshotRequest JSON from CreateComponentSnapshot and uploads staged PLY files from pending_snapshot_assets/{snapshot_id}/."
            inputs={[
              { label: 'SnapshotData', description: 'CreateSnapshotRequest JSON from CreateComponentSnapshot' },
              { label: 'Run', description: 'Toggle to execute the snapshot create operation' }
            ]}
            outputs={[
              { label: 'AddedSnapshotData', description: 'Compose response JSON ({identity, snapshots[]}) after create' }
            ]}
            tip="Validates the snapshot payload, posts the new version, and uploads any staged PLY files. Requires authentication."
            imagePath={resolveStatic('/gh-interface/csc_addcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_DisassembleComponent"
            description="Parses compose JSON ({identity, snapshots[]}) back into Grasshopper-compatible geometry and metadata. Type, material, and provenance come from identity; geometry, condition, descriptors, and frames come from snapshot."
            inputs={[
              { label: 'ComponentData', description: 'Compose JSON ({identity, snapshots[]}) fetched from the server.' }
            ]}
            outputs={[
              { label: 'ID', description: 'Identity ID (GUID)' },
              { label: 'Name', description: 'Snapshot name' },
              { label: 'Type', description: 'Component type (panel, beam, column, slab, rubble, brick, pipe, profile, connector, other)' },
              { label: 'Material', description: 'Component material' },
              { label: 'Color', description: 'Snapshot color as System.Drawing.Color' },
              { label: 'Location', description: 'Snapshot location as Point3d (X=latitude, Y=longitude, Z=0)' },
              { label: 'BoundingBox', description: 'Snapshot bounding box as Rhino.Geometry.BoundingBox' },
              { label: 'PCAFrame', description: 'Snapshot PCA frame at world origin as Rhino.Geometry.Plane' },
              { label: 'Descriptors', description: 'Snapshot descriptors/metadata as JSON string' },
              { label: 'PrimitiveGeometry', description: 'Rhino geometry objects (extrusions, meshes, point clouds)' },
              { label: 'MarkerPoints', description: 'Marker points as list of Point3d objects' },
              { label: 'Attributes', description: 'Identity attributes as JSON string' },
              { label: 'Condition', description: 'Snapshot condition grade (0=destroyed/retired, 1=poor, 2=average, 3=good)' },
              { label: 'ManufacturedAt', description: 'Identity manufacturing date as ISO-8601 UTC timestamp' },
              { label: 'ManufacturedPrecision', description: 'Identity precision qualifier for ManufacturedAt (exact, month, year, unknown)' },
              { label: 'SalvageSource', description: 'Identity salvage source (e.g. building name, site)' },
              { label: 'SalvagedAt', description: 'Identity salvage date as ISO-8601 UTC timestamp' },
              { label: 'ParentComponent', description: 'Parent identity IDs (GUIDs) from identity.parent_identities' },
              { label: 'ReinforcementJson', description: 'Reinforcement JSON strings ({spec, diameter, points}) in iframe space; one per bar, same format as CreateReinforcement' }
            ]}
            tip="Parses compose JSON into individual Grasshopper-compatible outputs for further processing. ReinforcementJson can be fed back into CreateComponentIdentity / CreateComponentSnapshot or reconstructed in Grasshopper."
            imagePath={resolveStatic('/gh-interface/csc_disassemblecomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_TransformComponent"
            description="Applies transformations to snapshot insertion frames for positioning and orientation."
            inputs={[
              { label: 'ComponentData', description: 'Compose JSON string ({identity, snapshots[]})' },
              { label: 'XForm', description: 'Rhino transform to apply to the snapshot insertion frame' }
            ]}
            outputs={[
              { label: 'XComponentData', description: 'Transformed compose JSON string ({identity, snapshots[]})' }
            ]}
            tip="Updates the snapshot's insertion frame with the applied transformation while preserving all other compose data."
            imagePath={resolveStatic('/gh-interface/csc_transformcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_GetComponentData"
            description="Extracts the csc_component compose data ({identity, snapshots[]} JSON string) from Rhino geometry objects. Safely retrieves and parses the compose data stored as user strings."
            inputs={[
              { label: 'Geometry', description: 'Geometry objects with the \'csc_component\' compose userdata' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'Compose JSON strings ({identity, snapshots[]}) extracted from geometry userdata' }
            ]}
            tip="Useful for retrieving compose data from geometry that was previously processed by CSC components."
            imagePath={resolveStatic('/gh-interface/csc_getcomponentdata.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_ApplyPCAFrame"
            description="Applies an inverse PCA transformation to align geometry or compose data with the world coordinate system, using the snapshot pca_frame. Takes either compose JSON ({identity, snapshots[]}) or Rhino geometry and transforms it to align with the world XY plane."
            inputs={[
              { label: 'Input', description: 'Compose JSON string ({identity, snapshots[]}) or geometry objects with the \'csc_component\' compose userdata' }
            ]}
            outputs={[
              { label: 'Output', description: 'Transformed compose JSON (if input was JSON) or transformed geometry with updated compose userdata (if input was geometry)' }
            ]}
            tip="Handles both compose JSON and geometry objects with compose userdata automatically."
            imagePath={resolveStatic('/gh-interface/csc_applypcaframe.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_CreateDesign"
            description="Creates a design JSON string from compose JSON ({identity, snapshots[]}), ready for posting to the Catalog. Pins each placement to a specific snapshot version and stores the design insertion iframe. Does NOT post the design - only generates the JSON string."
            inputs={[
              { label: 'DesignName', description: 'Design name (mandatory)' },
              { label: 'DesignDescription', description: 'Design description (optional)' },
              { label: 'ComponentData', description: 'List of compose JSON strings with snapshot.iframe set to the design placement' },
              { label: 'AdditionalGeometry', description: 'AdditionalGeometry (List of Mesh)' }
            ]}
            outputs={[
              { label: 'DesignJSON', description: 'Design JSON string ready for posting' }
            ]}
            tip="Automatically processes additional geometry meshes by centering them, computing iframes, and performing mesh reduction if needed."
            imagePath={resolveStatic('/gh-interface/csc_createdesign.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_AddDesign"
            description="Adds a new design to the remote database. Takes design data (JSON), validates it, and makes an authenticated POST request to add the design to the Catalog. Designs pin specific snapshot versions and may embed additional geometry directly in the JSON."
            inputs={[
              { label: 'DesignData', description: 'Design data as JSON string to add to the database' },
              { label: 'Run', description: 'Toggle to execute the add operation' }
            ]}
            outputs={[
              { label: 'AddedDesignData', description: 'The added design data returned from the server as JSON' }
            ]}
            tip="Validates design data including snapshot placements and additional geometry before posting to the database."
            imagePath={resolveStatic('/gh-interface/csc_adddesign.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_CreateUUID"
            description="Creates new UUIDs on request using an asynchronous callback mechanism."
            inputs={[
              { label: 'Refresh', description: 'If set to True, generates a new UUID' }
            ]}
            outputs={[
              { label: 'UUID', description: 'The current UUID' }
            ]}
            tip="UUIDs are cached and only regenerated when Refresh is toggled."
          />
        </div>
      )
    },
    {
      id: 'rhino-integration',
      title: 'Rhino Integration',
      icon: Settings,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Settings}
            name="CSC_BakeComponents"
            description="Bakes compose entries ({identity, snapshots[]}) into the Rhino document as meshes or primitive geometry."
            inputs={[
              { label: 'Bake', description: 'Toggle to bake components to Rhino' },
              { label: 'ComponentData', description: 'Compose JSON strings from FetchComponents' }
            ]}
            outputs={[
              { label: 'None', description: 'This component has no outputs' }
            ]}
            tip="Uses cached PLY meshes when available, falls back to snapshot extrusions/meshes. Bakes reinforcement bars as pipe Breps on CSC_COMPONENTS::{identity_id}::Reinforcement (on by default). Stores full compose JSON on csc_component user text."
            imagePath={resolveStatic('/gh-interface/csc_bakecomponents.jpg')}
          />

          <ComponentCard
            icon={Settings}
            name="CSC_SyncWithRhinoDoc"
            description="Reads baked objects from the Rhino document and updates snapshot.iframe in compose JSON."
            inputs={[
              { label: 'Sync', description: 'Trigger to sync components with Rhino document' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'DataTree of compose JSON with updated snapshot.iframe from text tags or geometry bounds' }
            ]}
            tip="Groups objects by identity._id. Prefers text-tag planes over combined bounding-box frames."
            imagePath={resolveStatic('/gh-interface/csc_syncwithrhinodoc.jpg')}
          />

        </div>
      )
    },
    {
      id: 'matchmaking-tools',
      title: 'Matchmaking Tools',
      icon: WandSparkles,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={WandSparkles}
            name="CSC_AssignmentPoints"
            description="Solves point-to-point assignment between design points and library points. Supports greedy assignment (default, FullCircle-compatible) and Hungarian assignment via SciPy for optimal matching."
            inputs={[
              { label: 'DesignPts', description: 'Design points as DataTree of numbers. Each branch is one point.' },
              { label: 'LibraryPts', description: 'Library points as DataTree of numbers. Each branch is one point.' },
              { label: 'Weights', description: 'Weights for weighted Euclidean distance. Optional; defaults to 1.0 in each dimension.' },
              { label: 'Scale', description: 'Scale factor used by Hungarian mode before optimization. Optional; default 1e3. Ignored by greedy mode.' },
              { label: 'Algorithm', description: "Algorithm selector. Optional; defaults to 'greedy'. Accepted values: 'greedy', 'hungarian'." }
            ]}
            outputs={[
              { label: 'Assignment', description: 'Assignment tree. Branch i contains the selected library index for design point i.' },
              { label: 'Cost', description: 'Assignment cost tree. Branch i contains the cost value for design point i.' }
            ]}
            tip="Use after embedding or descriptor-based feature extraction to match design requirements to catalog candidates."
          />
        </div>
      )
    },
    {
      id: 'geometry-tools',
      title: 'Geometry Tools',
      icon: Box,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Box}
            name="CSC_CreateReinforcement"
            description="Builds one inline reinforcement bar JSON object ({spec, diameter, points}) for CreateComponentIdentity / CreateComponentSnapshot."
            inputs={[
              { label: 'Polyline', description: 'Open centerline as Polyline or PolylineCurve (no curve conversion)' },
              { label: 'Spec', description: 'Reinforcement steel specification (e.g. B500B)' },
              { label: 'Diameter', description: 'Bar diameter in millimeters' }
            ]}
            outputs={[
              { label: 'ReinforcementJson', description: 'SnapshotReinforcement JSON string for geometry.reinforcements[]' }
            ]}
            tip="Merge one or many JSON strings into the Reinforcements input on CreateComponentIdentity or CreateComponentSnapshot. DisassembleComponent outputs the same JSON format in iframe space."
          />

          <ComponentCard
            icon={Box}
            name="CSC_ComputePCAOrientation"
            description="Computes Principal Component Analysis orientation for Mesh, Brep, Extrusion, or PointCloud geometry."
            inputs={[
              { label: 'Geometry', description: 'Input Rhino Geometry (Mesh, Brep, Extrusion, or PointCloud)' }
            ]}
            outputs={[
              { label: 'ObjectOrientedBBX', description: 'Object oriented bounding box, obtained using PCA, at the location of the input geometry' },
              { label: 'AlignedGeometry', description: 'Input geometry transformed using PCA method and centered at world origin' },
              { label: 'AlignedBBX', description: 'Object oriented bounding box transformed using the computed PCA frame, centered at the world origin' },
              { label: 'TranslationVector', description: 'Translation vector that was used to move the geometry to the world origin' },
              { label: 'PCAXForm', description: 'PCA frame that was used to transform the geometry converted to a Rhino XForm.' }
            ]}
            tip="Point clouds use their sample points (3D PCA), same as CreateComponentIdentity. Extrusions still use the 2D minimum-bounding-rectangle path."
            imagePath={resolveStatic('/gh-interface/csc_computepcaorientation.jpg')}
          />

          <ComponentCard
            icon={Box}
            name="CSC_FindLargestFlatSide"
            description="Finds the largest flat side of a mesh using optimized algorithm. Uses normal clustering and early termination heuristics for performance."
            inputs={[
              { label: 'InputMesh', description: 'Input Mesh for finding the largest flat side.' },
              { label: 'AngleTolerance', description: 'Angle tolerance for clustering normals.' },
              { label: 'DistanceTolerance', description: 'Distance tolerance' },
              { label: 'FaceCountThreshold', description: 'Face count threshold for large meshes. Meshes with face count above this value will be processed by sampling a subset of vertices. Defaults to 15.000' },
              { label: 'MaxSamples', description: 'Maximum points to sample for the fallback algorithm. Defaults to 5.000' }
            ]}
            outputs={[
              { label: 'FlatPlane', description: 'Flattest Plane found. Normal always points AWAY from the Mesh.' },
              { label: 'Points', description: 'Final Points that were used to fit the flat plane.' }
            ]}
            tip="Optimized algorithm for finding flat surfaces on meshes, with performance optimizations for large meshes.
Idea and prototype code by Alessandro Garruto. Refactored and integrated by Max Benjamin Eschenbach."
            imagePath={resolveStatic('/gh-interface/csc_findlargestflatside.jpg')}
          />

          <ComponentCard
            icon={Box}
            name="CSC_MaxInscribedQuad"
            description="Finds a maximum-area inscribed 4-point polygon (quadrilateral) inside each input closed polyline. Method 0: pure Rhino (default)."
            inputs={[
              { label: 'Curves', description: 'Closed boundary polylines (PolylineCurve). Each is processed independently.' },
              { label: 'MaxIter', description: 'Maximum iterations for the optimizer.' },
              { label: 'Tolerance', description: 'Containment tolerance for inside checks (default 0.01).' },
              { label: 'Starts', description: 'Multi-start count; more starts improves quality (default 64).' },
              { label: 'Seed', description: 'Random seed for reproducibility (default 42).' }
            ]}
            outputs={[
              { label: 'Quads', description: 'List of best inscribed quadrilaterals (Polyline).' },
              { label: 'Areas', description: 'Area of each quadrilateral.' }
            ]}
            tip="Finds the largest quadrilateral that fits inside closed polylines using optimization methods.
Idea and prototype code by Alessandro Garruto. Refactored and integrated by Max Benjamin Eschenbach."
            imagePath={resolveStatic('/gh-interface/csc_maxinscribedquad.jpg')}
          />

          <ComponentCard
            icon={Box}
            name="CSC_ExtrusionProfile"
            description="Extracts a profile curve from a Rhino Extrusion at a given profile index and relative height parameter."
            inputs={[
              { label: 'ExtrusionGeometry', description: 'Rhino.Geometry.Extrusion to extract the profile curve from' },
              { label: 'ProfileIndex', description: 'Index of the profile curve to extract. The outer profile has index 0.' },
              { label: 'ProfileParameter', description: 'Relative parameter along the extrusion height: 0 = bottom profile, 1 = top profile (default 0.5)' }
            ]}
            outputs={[
              { label: 'ProfileCurve', description: 'The extracted profile curve' }
            ]}
            tip="Useful when working with panel extrusions before creating catalog snapshots or computing 2D shape descriptors."
          />

          <ComponentCard
            icon={Box}
            name="CSC_RadialSignature"
            description="Computes a radial shape signature for planar boundary curves. Rotates each curve into its canonical rest position, casts evenly spaced rays from the centroid, and returns distances and boundary tangents at intersections. Mirrors the backend radial_signature module."
            inputs={[
              { label: 'Curves', description: 'Closed planar boundary curve(s). Polylines are used verbatim; other curves are approximated to polylines using document tolerance.' },
              { label: 'Resolution', description: 'Number of rays cast from the centroid (default 64, must be ≥ 3)' },
              { label: 'RestPositionAlign', description: 'If True (default), rotate each profile into canonical rest position before ray casting. If False, use the curve as-is (still centered).' },
              { label: 'NumAngles', description: 'Rotation samples for rest-position search over [0, π) (default 180, 1° steps)' }
            ]}
            outputs={[
              { label: 'Distances', description: 'Tree of centroid-to-boundary distances per ray, one branch per input curve' },
              { label: 'Tangents', description: 'Tree of unit boundary tangent vectors at each ray hit' },
              { label: 'HitPoints', description: 'Tree of intersection points in world coordinates (useful for visualisation)' },
              { label: 'Rays', description: 'Tree of ray lines in world coordinates (useful for visualisation)' },
              { label: 'RestCurves', description: 'Input curves in rest position (centroid at origin, canonical axes aligned with World XY)' },
              { label: 'RestPlanes', description: 'Rest-position plane per input curve (centroid origin, canonical X/Y alignment)' },
              { label: 'RestAngles', description: 'Rotation angle in degrees applied to reach rest position, per input curve' },
              { label: 'RestXForm', description: 'Transform mapping world coordinates into the rest frame' }
            ]}
            tip="Produces descriptor-compatible shape signatures for matching and classification workflows."
          />
        </div>
      )
    },
    {
      id: 'visualization',
      title: 'Visualization',
      icon: Sparkles,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Code}
            name="CSC_CreateArrangement"
            description="Arranges components in an even square grid based on their snapshot bounding boxes. Calculates grid cell size from the largest component dimension."
            inputs={[
              { label: 'ComponentData', description: 'Compose JSON strings ({identity, snapshots[]})' },
              { label: 'Spacing', description: 'Additional spacing between grid cells (default: 100.0)' },
              { label: 'InsertionPoint', description: 'Insertion point (starting corner of grid, default: 0,0,0)' }
            ]}
            outputs={[
              { label: 'GridCells', description: 'Grid cell outlines as polylines' },
              { label: 'GridPlanes', description: 'XY planes at center of each grid cell' },
              { label: 'XForm', description: 'Transformations from world origin to grid cell planes' }
            ]}
            tip="Automatically determines optimal grid size based on component bounding boxes."
            imagePath={resolveStatic('/gh-interface/csc_arrangecomponents.jpg')}
          />

          <ComponentCard
            icon={Sparkles}
            name="CSC_VisualizeEmbedding"
            description="Visualizes a low-dimensional embedding (e.g. from ComputePCA or ComputeTSNE) by placing associated geometry at embedding coordinates. Supports 1D, 2D, and 3D layouts; dimensions beyond the third are mapped to RGB colour channels."
            inputs={[
              { label: 'EmbeddedData', description: 'Embedded coordinates as a DataTree (one branch per datapoint). Output of ComputePCA or ComputeTSNE.' },
              { label: 'Geometry', description: 'Geometry to place in the layout as a DataTree. One branch per datapoint; branch order must match EmbeddedData.' },
              { label: 'ScaleFactor', description: 'Total layout extent in world units. Each dimension is min-max normalised to [0, ScaleFactor] (default 1000.0)' }
            ]}
            outputs={[
              { label: 'LayoutGeometry', description: 'Input geometry translated from its bounding-box centre to the corresponding embedding point' },
              { label: 'LayoutPoints', description: 'Embedding points in world coordinates (1D: Y=Z=0; 2D: Z=0)' },
              { label: 'Colors', description: 'Per-datapoint RGB from embedding dims 4–6 (missing channels default to mid-grey)' },
              { label: 'XForm', description: 'Translation transform applied to each input geometry' }
            ]}
            tip="Pair with ComputePCA or ComputeTSNE and descriptor/feature trees to explore catalog similarity clusters spatially."
          />
        </div>
      )
    },
    {
      id: 'utility-components',
      title: 'Utility Components',
      icon: HelpCircle,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={HelpCircle}
            name="CSC_ConvertGeoLocation"
            description="Converts a latitude/longitude string (e.g. copied from Google Maps) into numeric components and a Rhino vector for use with CreateComponentIdentity or CreateComponentSnapshot."
            inputs={[
              { label: 'LatLonString', description: 'Latitude, longitude string, e.g. "52.1231321, 9.1231231312"' }
            ]}
            outputs={[
              { label: 'Lat', description: 'Latitude as float' },
              { label: 'Lon', description: 'Longitude as float' },
              { label: 'Vec', description: 'Vector3d with lat/lon as X/Y (Z = 0)' }
            ]}
            tip="Wire Vec directly into the Location input of CreateComponentIdentity or CreateComponentSnapshot."
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_JSONKeys"
            description="Extracts all keys from a JSON object for exploring component data structure."
            inputs={[
              { label: 'JSON', description: 'JSON string to extract keys from' },
              { label: 'MaxDepth', description: 'Maximum depth to traverse in the JSON structure (default: 5)' }
            ]}
            outputs={[
              { label: 'Keys', description: 'List of all available keys in the JSON structure' },
              { label: 'Types', description: 'Data types for each key (object, array, string, number, boolean, null)' },
              { label: 'Paths', description: 'Full dot-notation paths for each key (e.g., "descriptors.material.type")' }
            ]}
            tip="Useful for exploring the structure of component data before extracting specific values."
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_JSONGetValue"
            description="Extracts specific values from JSON data using dot notation (e.g., 'geometry.meshes.0.v')."
            inputs={[
              { label: 'JSON', description: 'JSON string to extract value from' },
              { label: 'KeyPath', description: 'Dot-notation path to the desired value (e.g., "descriptors.material.type")' },
              { label: 'DefaultValue', description: 'Default value to return if key path is not found (optional)' }
            ]}
            outputs={[
              { label: 'Value', description: 'Extracted value converted to appropriate Grasshopper type' },
              { label: 'Type', description: 'Data type of the extracted value (string, number, boolean, object, array, null)' },
              { label: 'Success', description: 'True if extraction was successful, False otherwise' },
              { label: 'Error', description: 'Error message if extraction failed, empty string if successful' }
            ]}
            tip="Useful for extracting specific data from component JSON using dot notation paths."
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_ComputePCA"
            description="Computes principal component analysis (PCA) for dimensionality reduction."
            inputs={[
              { label: 'Data', description: 'Data to be reduced using PCA as a DataTree, where each Branch represents one DataPoint' },
              { label: 'Components', description: 'Dimension of the embedded space (default: 2)' }
            ]}
            outputs={[
              { label: 'EmbeddedData', description: 'The transformed data as a DataTree, where each Branch represents one embedded DataPoint' }
            ]}
            tip="Useful for dimensionality reduction of high-dimensional data into lower-dimensional spaces."
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_ComputeTSNE"
            description="Computes T-distributed Stochastic Neighbor Embedding for nonlinear dimensionality reduction."
            inputs={[
              { label: 'Data', description: 'Data to be reduced using t-SNE as a DataTree, where each Branch represents one DataPoint' },
              { label: 'Components', description: 'Dimension of the embedded space' },
              { label: 'Perplexity', description: 'The perplexity is related to the number of nearest neighbors. Consider selecting a value between 5 and 50. Defaults to 30' },
              { label: 'EarlyExaggeration', description: 'Controls how tight natural clusters in the original space are in the embedded space. Defaults to 12' },
              { label: 'LearningRate', description: 'The learning rate for t-SNE is usually in the range (10.0, 1000.0). Defaults to 200' },
              { label: 'Iterations', description: 'Maximum number of iterations for the optimization. Should be at least 250. Defaults to 1000' },
              { label: 'Method', description: 'Barnes-Hut approximation (0) runs in O(NlogN) time. Exact method (1) runs in O(N^2) time. Defaults to 0' },
              { label: 'Initialization', description: 'Initialization method. Random (0) or PCA (1). Defaults to 0' },
              { label: 'RandomSeed', description: 'Determines the random number generator. Pass an int for reproducible results. Defaults to None' }
            ]}
            outputs={[
              { label: 'EmbeddedData', description: 'The transformed data as a DataTree, where each Branch represents one embedded DataPoint' }
            ]}
            tip="T-SNE is great for visualizing high-dimensional data in 2D or 3D by preserving local neighborhood structure."
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_GetDescriptor"
            description="Retrieves a specific descriptor from multiple compose inputs ({identity, snapshots[]}). Accepts compose JSON strings or geometries with the csc_component userdata. Returns descriptor values for the specified key from snapshot.descriptors. Handles single values, lists, and nested lists by mapping them to appropriate Grasshopper data structures with input indices as the first path level."
            inputs={[
              { label: 'Input', description: 'List of compose JSON strings ({identity, snapshots[]}) OR geometries with the \'csc_component\' compose userdata' },
              { label: 'DescriptorKey', description: 'Key string to retrieve from snapshot.descriptors' }
            ]}
            outputs={[
              { label: 'DescriptorValues', description: 'Descriptor value for the specified key, or empty if not found. Output is structured as a DataTree with input indices as the first path level' }
            ]}
            tip="Handles complex nested descriptor structures automatically and preserves data tree paths from the input structure."
          />
        </div>
      )
    },
    {
      id: 'workflow-examples',
      title: 'Common Workflows',
      icon: BookOpen,
      content: (
        <div className="space-y-6 pt-2">

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Exploring Components</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_Session</strong></li>
                <li>Fetch all available components with <strong>CSC_FetchAllComponents</strong></li>
                <li>Filter results with <strong>CSC_FilterComponents</strong></li>
                <li>Work with geometry using <strong>CSC_DisassembleComponent</strong></li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Working with Reserved Components</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_Session</strong></li>
                <li>Fetch all your reserved components with <strong>CSC_FetchFilteredComponents</strong> (set ReservedStatus = 1)</li>
                <li>Work with geometry using <strong>CSC_DisassembleComponent</strong></li>
                <li>Release unused components using the web interface to make them available again</li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Creating a New Identity</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_Session</strong></li>
                <li>Optionally fetch a transmitted tag ID with <strong>CSC_FetchTransmittedID</strong> (after scanning in the web UI)</li>
                <li>Build the create payload with <strong>CSC_CreateComponentIdentity</strong> (wire the identity UUID from step 2 or CreateUUID)</li>
                <li>Post to the catalog with <strong>CSC_AddComponentIdentity</strong> — returns compose JSON ({`{identity, snapshots[]}`})</li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Adding a New Snapshot Version</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_Session</strong></li>
                <li>Know the existing identity UUID (from fetch, disassemble, or physical tag)</li>
                <li>Build the snapshot payload with <strong>CSC_CreateComponentSnapshot</strong></li>
                <li>Post the new version with <strong>CSC_AddComponentSnapshot</strong></li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Exploring Data</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Fetch component data with <strong>CSC_FetchComponents</strong></li>
                <li>Extract available descriptors with <strong>CSC_GetDescriptor</strong></li>
                <li>Process the data in your Grasshopper definition, i.e. by categorizing and sorting components</li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Creating Designs</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_Session</strong></li>
                <li>Fetch compose JSON with <strong>CSC_FetchComponents</strong> and place with <strong>CSC_SyncWithRhinoDoc</strong></li>
                <li>Create design with <strong>CSC_CreateDesign</strong> from compose JSON (includes additional geometry)</li>
                <li>Save design to database with <strong>CSC_AddDesign</strong></li>
                <li>Fetch and work with design using <strong>CSC_FetchDesign</strong></li>
              </ol>
            </div>
          </div>

        </div>
      )
    }
  ]

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="mb-8">
        <h1 className="mb-3 flex items-center gap-2 text-2xl font-bold">
          <Terminal className="h-6 w-6 text-primary" />
          Grasshopper Interface
        </h1>
        <p className="text-lg text-muted-foreground">
          Learn how to use the DDU CSC Grasshopper components to work with the Catalog of Second Chances.
        </p>
      </div>

      <div className="space-y-4">
        {sections.map((section) => {
          const Icon = section.icon
          const isExpanded = expandedSections.has(section.id)
          
          return (
            <div key={section.id} data-section-id={section.id} className="border rounded-lg bg-muted">
              <button
                onClick={() => toggleSection(section.id)}
                className="w-full px-6 py-4 text-left flex items-center justify-between hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Icon className="h-5 w-5" />
                  <h2 className="text-lg font-semibold">{section.title}</h2>
                </div>
                {isExpanded ? (
                  <ChevronDown className="h-5 w-5" />
                ) : (
                  <ChevronRight className="h-5 w-5" />
                )}
              </button>
              
              {isExpanded && (
                <div className="px-6 pb-6 border-t">
                  {section.content}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-12 bg-muted/50 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <HelpCircle className="h-5 w-5" />
          Need Help?
        </h3>
        <p className="text-muted-foreground mb-4">
          If you encounter issues or need additional support:
        </p>
        <ul className="text-sm text-muted-foreground space-y-2">
          <li>• Check the component runtime messages for error details</li>
          <li>• Ensure you&apos;re properly authenticated with <strong>CSC_Session</strong></li>
          <li>• Verify your internet connection for API access</li>
          <li>• Contact <a href={`mailto:eschenbach@dg.tu-darmstadt.de?subject=[CSC]%20Support%20Request%20by%20user&body=Please%20describe%20the%20issue%20you%20are%20facing%20in%20detail.%20Include%20any%20error%20messages%20or%20logs%20you%20have%20received.`} className='text-blue-500 underline'>Max</a> via e-mail or various messenger apps</li>
        </ul>
      </div>
    </div>
  )
}