'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import { resolveStatic } from '@/lib/utils'
import { Terminal, BookOpen, Code, Database, Settings, HelpCircle, ChevronRight, ChevronDown, FileImage, Download, Check, FileText, ArrowRight, WandSparkles, Sparkles, Box } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

export default function GHInterfacePage() {
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

  // Fetch release version on component mount
  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const response = await fetch('/api/backend/downloads/gh-interface/version')
        if (response.ok) {
          const data = await response.json()
          setReleaseVersion(data.version || '')
        }
      } catch (error) {
        console.error('Failed to fetch release version:', error)
      }
    }
    
    fetchVersion()
  }, [])

  const handleDownload = async () => {
    setIsDownloading(true)
    try {
      const response = await fetch('/api/backend/downloads/gh-interface')
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
        const res = await fetch(`/api/backend/ghupdates/xml/${encodeURIComponent(xmlName)}`)
        if (!res.ok) {
          console.error('Failed to fetch XML:', res.status)
          alert('XML not available for this component.')
          return
        }
        const xmlText = await res.text()
        await navigator.clipboard.writeText(xmlText)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch (err) {
        console.error('Copy XML error:', err)
        alert('Copy to clipboard failed.')
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

          <p className="text-muted-foreground">
            The DDU CSC Grasshopper Interface provides components for working with the Catalog of Second Chances. This tutorial covers each component and their usage.
          </p>

          <div className="bg-purple-50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
            <h4 className="font-semibold text-purple-900 dark:text-purple-100 mb-2 flex items-center gap-2">
              <FileText className="h-4 w-4" />
              NEW! Automatic Updater
            </h4>
            <p className="text-sm text-purple-800 dark:text-purple-200 mb-3">
              Make your life easier and keep your CSC Grasshopper components up-to-date without headache! Use the new <strong>CSC_Update</strong> component to check for and install updates from the server.
            </p>
            <div className="flex items-center gap-3">
              {/* Find out more Interface */}
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  // Expand the authentication section if not already expanded
                  if (!expandedSections.has('authentication')) {
                    toggleSection('authentication')
                  }
                  // Wait for section to expand, then scroll to the CSC_Update card
                  setTimeout(() => {
                    const updateCard = document.querySelector('[data-component-card="CSC_Update"]')
                    if (updateCard) {
                      updateCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    } else {
                      // Fallback to section if card not found
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
              {/* Copy GH Component XML Interface */}
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={async () => {
                        try {
                          const xmlName = 'DDU_CSC_Update'
                          const res = await fetch(`/api/backend/ghupdates/xml/${encodeURIComponent(xmlName)}`)
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
            name="CSC_FetchComponents"
            description="Fetches specific components from the remote Catalog by their IDs. Supports caching and handles individual component retrieval with error handling for missing components."
            inputs={[
              { label: 'ComponentID', description: 'One or many ComponentIDs to fetch' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'The ComponentData that was fetched from the server as JSON. Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="Supports caching for faster subsequent access. Handles missing components gracefully."
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
            description="Filters a list of component data based on various criteria (type, material, dataset, complexity, fragment, bounding box dimensions). Works with local component data."
            inputs={[
              { label: 'Type', description: 'Component type filter (e.g., "beam", "slab", "column")' },
              { label: 'Material', description: 'Material type filter (e.g., "concrete", "steel", "wood")' },
              { label: 'Dataset', description: 'Dataset name filter (e.g., "sas_cita_scans", "mineral_composite_sheets")' },
              { label: 'Complexity', description: 'Complexity level filter (0-3, where 0=simple, 3=complex)' },
              { label: 'Fragment', description: 'Fragment status filter (True for fragments, False for complete)' },
              { label: "MinDimensionX", description: "Minimum X dimension filter (bounding box)" },
              { label: "MaxDimensionX", description: "Maximum X dimension filter (bounding box)" },
              { label: "MinDimensionY", description: "Minimum Y dimension filter (bounding box)" },
              { label: "MaxDimensionY", description: "Maximum Y dimension filter (bounding box)" },
              { label: "MinDimensionZ", description: "Minimum Z dimension filter (bounding box)" },
              { label: "MaxDimensionZ", description: "Maximum Z dimension filter (bounding box)" },
              { label: 'ComponentData', description: 'Component data to filter (from FetchComponents or similar)' },
            ]}
            outputs={[
              { label: 'FilterDescription', description: 'Human-readable description of the applied filters' },
              { label: 'FilteredComponentData', description: 'Filtered ComponentData as JSON strings. Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="Works with local component data. Use after FetchComponents or FetchAllComponents to filter results locally."
            imagePath={resolveStatic('/gh-interface/csc_filtercomponents.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchFilteredComponents"
            description="Fetches components from the remote Catalog based on filter criteria (type, material, dataset, complexity, dimensions, reservation status). Builds query parameters and returns filtered results."
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
              { label: 'ComponentData', description: 'The ComponentData that was fetched from the server as JSON. Use \'DisassembleComponent\' to access the individual fields ready for Grasshopper' }
            ]}
            tip="More efficient than fetching all components and filtering locally. Use this for large datasets with server-side filtering."
            imagePath={resolveStatic('/gh-interface/csc_fetchfilteredcomponents.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchGeometry"
            description="Fetches detailed, reduced, or primitive geometry for a component from the API or local cache. Converts OBJ data to Rhino geometry objects and applies iframe transformations from the component json."
            inputs={[
              { label: 'Input', description: 'Input can be:\na) A geometry object with \'csc_component\' userstring\nb) A JSON string containing component data\nc) Just the component _id' },
              { label: 'Detailed', description: 'True for detailed geometry, False for reduced' }
            ]}
            outputs={[
              { label: 'GeometryData', description: 'Fetched geometry as Rhino.Geometry.GeometryBase objects (can be multiple meshes)' },
              { label: 'GeometryType', description: 'Geometry type: detailed, reduced, or primitive' },
              { label: 'ComponentID', description: 'Component ID that was processed' }
            ]}
            tip="Falls back to primitive geometry if no additional geometry exists. Supports multiple input formats for flexibility."
            imagePath={resolveStatic('/gh-interface/csc_fetchgeometry.jpg')}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchDesign"
            description="Fetches a design from the remote Catalog along with all its contained components. Updates each component's iframe with the design's iframe and returns both design JSON and components with updated iframes. Uses caching for optimal performance."
            inputs={[
              { label: 'DesignID', description: 'Design ID to fetch' }
            ]}
            outputs={[
              { label: 'DesignData', description: 'Design JSON string' },
              { label: 'ComponentData', description: 'Components with updated iframes from design' },
              { label: 'AdditionalGeometryData', description: 'Additional geometry items (list of JSON strings)' },
              { label: 'AdditionalGeometry', description: 'Additional geometry as Rhino meshes' }
            ]}
            tip="Designs contain both component references and embedded additional geometry. Components are automatically updated with the design's iframe."
            imagePath={resolveStatic('/gh-interface/csc_fetchdesign.jpg')}
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
            name="CSC_CreateComponent"
            description="Creates a complete component JSON string from input geometry. Computes PCA orientation, handles mesh reduction, saves geometry files locally, and builds component data according to the schema."
            inputs={[
              { label: 'ClearLocalStorage', description: 'If set to True, clears all stored locally saved geometry files for component creation' },
              { label: 'ComponentID', description: 'Component ID (must be a valid UUID)' },
              { label: 'Type', description: 'Component type (e.g., "panel", "rubble"). Must be one of the values exposed by the backend component type enum.' },
              { label: 'Material', description: 'Material type (e.g., "steel", "concrete", "wood")' },
              { label: 'Dataset', description: 'Dataset that this component belongs to (i.e. my_rubble_dataset)' },
              { label: 'Complexity', description: 'Complexity level (0=simple, 1=normal, 2=complex, 3=very complex)' },
              { label: 'Fragment', description: 'Fragment status (True for fragments, False for complete)' },
              { label: 'Assembly', description: 'Assembly status (True for assemblies, False for individual)' },
              { label: 'Location', description: 'Location as Vector3d (X=latitude, Y=longitude, Z ignored)' },
              { label: 'Color', description: 'Component color (System.Drawing.Color)' },
              { label: 'Geometry', description: 'Rhino geometry object(s) - single object or list of objects. For single: Mesh or Extrusion for panels, Mesh for rubble. For multiple: list of Meshes' },
              { label: 'MarkerPoints', description: 'Marker points as list of Point3d objects for component identification and positioning' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'Component data as JSON string adhering to ComponentModel structure. Contains geometry, PCA frame, bounding box, and metadata.' }
            ]}
            tip="Automatically centers geometry at origin, computes PCA frames, handles mesh reduction, and saves geometry files locally for complex meshes."
            imagePath={resolveStatic('/gh-interface/csc_createcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_AddComponent"
            description="Adds a created component to the Catalog of Second Chances database."
            inputs={[
              { label: 'ComponentData', description: 'Component data as JSON string to add to the database' },
              { label: 'Run', description: 'Toggle to execute the add operation' }
            ]}
            outputs={[
              { label: 'AddedComponentData', description: 'The added component data returned from the server as JSON' }
            ]}
            tip="Validates component data before posting to the database. Requires authentication."
            imagePath={resolveStatic('/gh-interface/csc_addcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_DisassembleComponent"
            description="Converts component JSON data back into Grasshopper-compatible geometry and metadata."
            inputs={[
              { label: 'ComponentData', description: 'The ComponentData that was fetched from the server as JSON.' }
            ]}
            outputs={[
              { label: 'ID', description: 'Component ID (GUID)' },
              { label: 'Name', description: 'Human readable component name' },
              { label: 'Type', description: 'Component type (panel, beam, column, slab, rubble, brick, pipe, profile, connector, other)' },
              { label: 'Material', description: 'Component material' },
              { label: 'Color', description: 'Component color as System.Drawing.Color' },
              { label: 'Location', description: 'Component location as Point3d (X=latitude, Y=longitude, Z=0)' },
              { label: 'BoundingBox', description: 'Component bounding box as Rhino.Geometry.BoundingBox' },
              { label: 'PCAFrame', description: 'PCA frame at world origin as Rhino.Geometry.Plane' },
              { label: 'Descriptors', description: 'Component descriptors/metadata as JSON string' },
              { label: 'PrimitiveGeometry', description: 'Rhino geometry objects (extrusion, mesh, multiple meshes, polyline)' },
              { label: 'MarkerPoints', description: 'Marker points as list of Point3d objects' },
              { label: 'Attributes', description: 'Component attributes as JSON string' },
              { label: 'Condition', description: 'Component condition grade (0=destroyed/retired, 1=poor, 2=average, 3=good)' },
              { label: 'ManufacturedAt', description: 'Component manufacturing date as ISO-8601 UTC timestamp' },
              { label: 'ManufacturedPrecision', description: 'Precision qualifier for ManufacturedAt (exact, month, year, unknown)' },
              { label: 'SalvageSource', description: 'Component salvage source (e.g. building name, site)' },
              { label: 'SalvagedAt', description: 'Component salvage date as ISO-8601 UTC timestamp' },
              { label: 'ParentComponent', description: 'Parent component ID (GUID) this component was derived from' }
            ]}
            tip="Converts JSON component data into individual Grasshopper-compatible outputs for further processing."
            imagePath={resolveStatic('/gh-interface/csc_disassemblecomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_TransformComponent"
            description="Applies transformations to component insertion frames for positioning and orientation."
            inputs={[
              { label: 'ComponentData', description: 'JSON string containing component data' },
              { label: 'XForm', description: 'Rhino transform to apply to the insertion frame' }
            ]}
            outputs={[
              { label: 'XComponentData', description: 'Transformed component data as JSON string' }
            ]}
            tip="Updates the component's insertion frame with the applied transformation while preserving all other component data."
            imagePath={resolveStatic('/gh-interface/csc_transformcomponent.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_ArrangeComponents"
            description="Arranges components in an even square grid based on their bounding boxes. Calculates grid cell size from the largest component dimension."
            inputs={[
              { label: 'ComponentData', description: 'Component data as JSON strings' },
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
            icon={Code}
            name="CSC_GetComponentData"
            description="Extracts the csc_component user data (JSON string) from Rhino geometry objects. Safely retrieves and parses component data stored as user strings."
            inputs={[
              { label: 'Geometry', description: 'Geometry objects with component userdata' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'Component data as JSON strings extracted from geometry userdata' }
            ]}
            tip="Useful for retrieving component information from geometry that was previously processed by CSC components."
            imagePath={resolveStatic('/gh-interface/csc_getcomponentdata.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_ApplyPCAFrame"
            description="Applies an inverse PCA transformation to align geometry or component data with the world coordinate system. Takes either component JSON or Rhino geometry and transforms it to align with the world XY plane."
            inputs={[
              { label: 'Input', description: 'ComponentData (JSON string) or geometry objects with component userdata' }
            ]}
            outputs={[
              { label: 'Output', description: 'Transformed ComponentData (if input was JSON) or transformed geometry with updated userdata (if input was geometry)' }
            ]}
            tip="Handles both JSON component data and geometry objects with component userdata automatically."
            imagePath={resolveStatic('/gh-interface/csc_applypcaframe.jpg')}
          />

          <ComponentCard
            icon={Code}
            name="CSC_CreateDesign"
            description="Creates a design JSON string from component data, ready for posting to the Catalog. Validates input against design schema and generates complete design payload with UUID, timestamps, and component references. Does NOT post the design - only generates the JSON string."
            inputs={[
              { label: 'DesignName', description: 'Design name (mandatory)' },
              { label: 'DesignDescription', description: 'Design description (optional)' },
              { label: 'ComponentData', description: 'List of component JSON strings' },
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
            description="Adds a new design to the remote database. Takes design data (JSON), validates it, and makes an authenticated POST request to add the design to the Catalog. Designs contain component references and additional geometry embedded directly in the JSON."
            inputs={[
              { label: 'DesignData', description: 'Design data as JSON string to add to the database' },
              { label: 'Run', description: 'Toggle to execute the add operation' }
            ]}
            outputs={[
              { label: 'AddedDesignData', description: 'The added design data returned from the server as JSON' }
            ]}
            tip="Validates design data including component references and additional geometry before posting to the database."
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
            description="Bakes component geometry from Grasshopper into the Rhino document as actual Rhino objects."
            inputs={[
              { label: 'Bake', description: 'Toggle to bake components to Rhino' },
              { label: 'ComponentData', description: 'Component data from FetchComponents' }
            ]}
            outputs={[
              { label: 'None', description: 'This component has no outputs' }
            ]}
            tip="Converts Grasshopper component data into actual Rhino objects in the document."
            imagePath={resolveStatic('/gh-interface/csc_bakecomponents.jpg')}
          />

          <ComponentCard
            icon={Settings}
            name="CSC_SyncWithRhinoDoc"
            description="Synchronizes component data with the current Rhino document."
            inputs={[
              { label: 'Sync', description: 'Trigger to sync components with Rhino document' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'DataTree containing all component data found in the document, with updated iframe information based on current object positions' }
            ]}
            tip="Updates component iframe information based on current object positions in the Rhino document."
            imagePath={resolveStatic('/gh-interface/csc_syncwithrhinodoc.jpg')}
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
            name="CSC_ComputePCAOrientation"
            description="Computes Principal Component Analysis orientation for geometry alignment."
            inputs={[
              { label: 'Geometry', description: 'Input Rhino Geometry' }
            ]}
            outputs={[
              { label: 'ObjectOrientedBBX', description: 'Object oriented bounding box, obtained using PCA, at the location of the input geometry' },
              { label: 'AlignedGeometry', description: 'Input geometry transformed using PCA method and centered at world origin' },
              { label: 'AlignedBBX', description: 'Object oriented bounding box transformed using the computed PCA frame, centered at the world origin' },
              { label: 'TranslationVector', description: 'Translation vector that was used to move the geometry to the world origin' },
              { label: 'PCAXForm', description: 'PCA frame that was used to transform the geometry converted to a Rhino XForm.' }
            ]}
            tip="Computes PCA-based orientation for geometry alignment and provides transformation data for positioning."
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
            description="Extracts specific values from JSON data using dot notation (e.g., 'geometry.mesh.v')."
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
            description="Retrieves a specific descriptor from multiple component_data inputs. Accepts a list of component_data JSON strings or geometries with attached component_data. Returns the descriptor values for the specified key from the descriptors array. Handles single values, lists, and nested lists by mapping them to appropriate Grasshopper data structures with input indices as the first path level."
            inputs={[
              { label: 'Input', description: 'List of component data as JSON strings OR geometries with attached component_data userdata' },
              { label: 'DescriptorKey', description: 'Key string to retrieve from the descriptors array in component_data' }
            ]}
            outputs={[
              { label: 'DescriptorValues', description: 'Descriptor value for the specified key, or empty if not found. Output is structured as a DataTree with input indices as the first path level' }
            ]}
            tip="Handles complex nested data structures automatically and preserves data tree paths from the input structure."
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
                <li>Fetch all your reserved components with <strong>CSC_FetchFilteredComponents</strong></li>
                <li>Work with geometry using <strong>CSC_DisassembleComponent</strong></li>
                <li>Release unused components using the web interface to make them available again</li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Creating Components</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_Session</strong></li>
                <li>Process your own geometry with <strong>CSC_CreateComponent</strong></li>
                <li>Save to database with <strong>CSC_AddComponent</strong></li>
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
                <li>Create components with <strong>CSC_CreateComponent</strong></li>
                <li>Create design with <strong>CSC_CreateDesign</strong> (includes additional geometry)</li>
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
        <h1 className="text-3xl font-bold mb-4 flex items-center gap-3">
          <Terminal className="h-8 w-8 text-primary" />
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
          <li>• Ensure you&apos;re properly authenticated with CSC_SignIn</li>
          <li>• Verify your internet connection for API access</li>
          <li>• Contact <a href={`mailto:eschenbach@dg.tu-darmstadt.de?subject=[CSC]%20Support%20Request%20by%20user&body=Please%20describe%20the%20issue%20you%20are%20facing%20in%20detail.%20Include%20any%20error%20messages%20or%20logs%20you%20have%20received.`} className='text-blue-500 underline'>Max</a> via e-mail or various messenger apps</li>
        </ul>
      </div>
    </div>
  )
}