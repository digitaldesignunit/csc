'use client'

import { useState } from 'react'
import { Terminal, BookOpen, Code, Database, Settings, HelpCircle, ChevronRight, ChevronDown, Image, Download } from 'lucide-react'

export default function GHInterfacePage() {
  const [expandedSection, setExpandedSection] = useState<string | null>('getting-started')

  const toggleSection = (sectionId: string) => {
    setExpandedSection(expandedSection === sectionId ? null : sectionId)
  }

  const ComponentCard = ({ 
    icon: Icon, 
    name, 
    description, 
    inputs, 
    outputs, 
    tip 
  }: {
    icon: any
    name: string
    description: string
    inputs: Array<{label: string, description: string}>
    outputs: Array<{label: string, description: string}>
    tip?: string
  }) => (
    <div className="border rounded-lg p-4">
      <div className="w-full h-64 bg-muted rounded-lg flex items-center justify-center border-2 border-dashed border-muted-foreground/25 mb-4">
        <div className="text-center text-muted-foreground">
          <Image className="h-12 w-12 mx-auto mb-3" />
          <p className="text-lg font-medium">{name}</p>
          <p className="text-sm">Component Screenshot</p>
        </div>
      </div>
      <div>
        <h4 className="font-semibold text-lg mb-3 flex items-center gap-2">
          <Icon className="h-5 w-5" />
          {name}
        </h4>
        <p className="text-muted-foreground mb-3">
          {description}
        </p>
        <div className="space-y-3">
          <div>
            <h5 className="font-medium text-sm mb-1">Inputs:</h5>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              {inputs.map((input, index) => (
                <li key={index}>
                  • <strong>{input.label}:</strong> {input.description}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h5 className="font-medium text-sm mb-1">Outputs:</h5>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              {outputs.map((output, index) => (
                <li key={index}>
                  • <strong>{output.label}:</strong> {output.description}
                </li>
              ))}
            </ul>
          </div>
          {tip && (
            <div className="bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded p-3">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                <strong>Tip:</strong> {tip}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )

  const sections = [
    {
      id: 'getting-started',
      title: 'Getting Started',
      icon: BookOpen,
      content: (
        <div className="space-y-6 pt-2">
          <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <h4 className="font-semibold text-green-900 dark:text-green-100 mb-2 flex items-center gap-2">
              <Download className="h-4 w-4" />
              Download Grasshopper Interface
            </h4>
            <p className="text-sm text-green-800 dark:text-green-200 mb-3">
              Download the complete Grasshopper interface with all user objects and example files.
            </p>
            <div className="flex gap-3">
              <button className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer">
                Download Interface (.zip)
              </button>
            </div>
          </div>

          <p className="text-muted-foreground">
            The DDU CSC Grasshopper Interface provides components for working with the Catalogue of Second Chances. This tutorial covers each component and their usage.
          </p>
          
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
      title: 'Authentication Components',
      icon: Settings,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Terminal}
            name="CSC_SignIn"
            description="Connects your Grasshopper session to the Catalogue of Second Chances. Required before using other components."
            inputs={[
              { label: 'Username', description: 'Your CSC username or email' },
              { label: 'Password', description: 'Your CSC password' },
              { label: 'Refresh', description: 'Refresh authentication when token expires' },
              { label: 'DisableCache', description: 'Disable local caching (optional)' },
              { label: 'ClearCache', description: 'Clear local cache (optional)' }
            ]}
            outputs={[
              { label: 'Status', description: 'Authentication status and cache info' }
            ]}
            tip="Automatically caches authentication and component data locally for faster access."
          />
        </div>
      )
    },
    {
      id: 'catalogue-interface',
      title: 'Catalogue Interface Components',
      icon: Database,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Database}
            name="CSC_FetchComponents"
            description="Retrieves specific components from the catalogue using their UUIDs."
            inputs={[
              { label: 'ComponentID', description: 'One or more component UUIDs to fetch' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'JSON data for the fetched components' }
            ]}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchAllComponents"
            description="Retrieves all components from the catalogue. Use with caution for large datasets."
            inputs={[
              { label: 'Refresh', description: 'Force refresh from server' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'JSON data for all components' }
            ]}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FilterComponents"
            description="Filters components by type, material, complexity, and dimensions."
            inputs={[
              { label: 'ComponentData', description: 'Input component data to filter' },
              { label: 'Type', description: 'Component type (e.g., "sheet", "rubble")' },
              { label: 'Material', description: 'Material type (e.g., "steel", "concrete")' },
              { label: 'Complexity', description: 'Complexity level (0-3)' },
              { label: 'Fragment', description: 'Fragment status (True/False)' },
              { label: 'Min/Max X/Y/Z', description: 'Bounding box dimensions' }
            ]}
            outputs={[
              { label: 'FilteredData', description: 'Components matching filter criteria' }
            ]}
          />

          <ComponentCard
            icon={Database}
            name="CSC_FetchGeometry"
            description="Retrieves geometry data for specific components."
            inputs={[
              { label: 'ComponentID', description: 'UUID of the component to fetch geometry for' }
            ]}
            outputs={[
              { label: 'Geometry', description: 'Rhino geometry objects (meshes, extrusions)' }
            ]}
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
            description="Creates a new component from Rhino geometry with automatic PCA analysis and bounding box calculation."
            inputs={[
              { label: 'ComponentID', description: 'Unique UUID for the component' },
              { label: 'Type', description: 'Component type ("sheet" or "rubble")' },
              { label: 'Material', description: 'Material type (e.g., "steel", "concrete")' },
              { label: 'Complexity', description: 'Complexity level (0-3)' },
              { label: 'Fragment', description: 'Fragment status (True/False)' },
              { label: 'Assembly', description: 'Assembly status (True/False)' },
              { label: 'Color', description: 'Component color (System.Drawing.Color)' },
              { label: 'Location', description: 'Geographic location (Vector3d: X=lat, Y=lon)' },
              { label: 'Geometry', description: 'Rhino geometry object(s)' },
              { label: 'MarkerPoints', description: 'Optional identification points' }
            ]}
            outputs={[
              { label: 'ComponentData', description: 'Complete component data as JSON' }
            ]}
            tip="Automatically centers geometry at origin, computes PCA frames, and creates geometry files for complex meshes."
          />

          <ComponentCard
            icon={Code}
            name="CSC_AddComponent"
            description="Adds a created component to the Catalogue of Second Chances database."
            inputs={[
              { label: 'ComponentData', description: 'JSON component data from CreateComponent' },
              { label: 'Run', description: 'Execute the add operation' }
            ]}
            outputs={[
              { label: 'AddedComponentData', description: 'Server response with added component data' }
            ]}
          />

          <ComponentCard
            icon={Code}
            name="CSC_DisassembleComponent"
            description="Converts component JSON data back into Grasshopper-compatible geometry and metadata."
            inputs={[
              { label: 'ComponentData', description: 'JSON component data from FetchComponents' }
            ]}
            outputs={[
              { label: 'Geometry', description: 'Rhino geometry objects' },
              { label: 'BoundingBox', description: 'Component bounding box' },
              { label: 'InsertionFrame', description: 'Component insertion frame' },
              { label: 'PCAFrame', description: 'Principal component analysis frame' },
              { label: 'Metadata', description: 'Component properties and attributes' }
            ]}
          />

          <ComponentCard
            icon={Code}
            name="CSC_TransformComponent"
            description="Applies transformations to component insertion frames for positioning and orientation."
            inputs={[
              { label: 'ComponentData', description: 'JSON component data' },
              { label: 'XForm', description: 'Rhino transform to apply' }
            ]}
            outputs={[
              { label: 'TransformedData', description: 'Component data with updated insertion frame' }
            ]}
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
              { label: 'Geometry', description: 'Rhino geometry objects to bake' },
              { label: 'LayerName', description: 'Layer name for baked objects (optional)' },
              { label: 'Bake', description: 'Execute the baking operation' }
            ]}
            outputs={[
              { label: 'ObjectIDs', description: 'Rhino object IDs of baked geometry' }
            ]}
          />

          <ComponentCard
            icon={Settings}
            name="CSC_SyncWithRhinoDoc"
            description="Synchronizes component data with the current Rhino document."
            inputs={[
              { label: 'Sync', description: 'Execute synchronization' }
            ]}
            outputs={[
              { label: 'Status', description: 'Synchronization status and information' }
            ]}
          />

          <ComponentCard
            icon={Settings}
            name="CSC_ViewCaptureToFile"
            description="Captures the current Rhino view to an image file for documentation."
            inputs={[
              { label: 'FilePath', description: 'Full path where to save the image' },
              { label: 'Width', description: 'Image width in pixels (optional)' },
              { label: 'Height', description: 'Image height in pixels (optional)' },
              { label: 'Capture', description: 'Execute the capture' }
            ]}
            outputs={[
              { label: 'Success', description: 'Capture success status' },
              { label: 'FilePath', description: 'Actual file path where image was saved' }
            ]}
          />
        </div>
      )
    },
    {
      id: 'development-tools',
      title: 'Development Tools',
      icon: Code,
      content: (
        <div className="space-y-6 pt-2">
          <ComponentCard
            icon={Code}
            name="CSC_ExportScriptsAndSource"
            description="Exports Grasshopper definitions and source code for development and backup."
            inputs={[
              { label: 'ExportPath', description: 'Directory path where to export files' },
              { label: 'Export', description: 'Execute the export' }
            ]}
            outputs={[
              { label: 'Status', description: 'Export status and file information' }
            ]}
          />

          <ComponentCard
            icon={Code}
            name="CSC_SaveAndSaveGHX"
            description="Saves the current Grasshopper definition in both .gh and .ghx formats."
            inputs={[
              { label: 'FilePath', description: 'Base file path (without extension)' },
              { label: 'Save', description: 'Execute the save operation' }
            ]}
            outputs={[
              { label: 'Status', description: 'Save operation status' }
            ]}
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
              { label: 'JSON', description: 'JSON string to extract keys from' }
            ]}
            outputs={[
              { label: 'Keys', description: 'List of all JSON keys' }
            ]}
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_JSONGetValue"
            description="Extracts specific values from JSON data using dot notation (e.g., 'geometry.mesh.v')."
            inputs={[
              { label: 'JSON', description: 'JSON string to extract from' },
              { label: 'KeyPath', description: 'Dot notation path (e.g., "geometry.mesh.v")' }
            ]}
            outputs={[
              { label: 'Value', description: 'Extracted value from the specified path' }
            ]}
          />

          <ComponentCard
            icon={HelpCircle}
            name="CSC_ComputePCAOrientation"
            description="Computes Principal Component Analysis orientation for geometry alignment."
            inputs={[
              { label: 'Geometry', description: 'Rhino geometry object to analyze' }
            ]}
            outputs={[
              { label: 'PCAAxes', description: 'Principal component axes as vectors' },
              { label: 'Dimensions', description: 'Bounding box dimensions in PCA space' }
            ]}
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
            <h4 className="font-semibold text-lg mb-3">Creating Components</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_SignIn</strong></li>
                <li>Process geometry with <strong>CSC_CreateComponent</strong></li>
                <li>Save to database with <strong>CSC_AddComponent</strong></li>
                <li>Convert back to geometry with <strong>CSC_DisassembleComponent</strong></li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Finding Components</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Authenticate with <strong>CSC_SignIn</strong></li>
                <li>Fetch components with <strong>CSC_FetchAllComponents</strong></li>
                <li>Filter results with <strong>CSC_FilterComponents</strong></li>
                <li>Work with geometry using <strong>CSC_DisassembleComponent</strong></li>
              </ol>
            </div>
          </div>

          <div className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">Exploring Data</h4>
            <div className="space-y-3">
              <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                <li>Fetch component data with <strong>CSC_FetchComponents</strong></li>
                <li>View available fields with <strong>CSC_JSONKeys</strong></li>
                <li>Extract specific values with <strong>CSC_JSONGetValue</strong></li>
                <li>Process the data in your Grasshopper definition</li>
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
          <Terminal className="h-8 w-8" />
          Grasshopper Interface Tutorial
        </h1>
        <p className="text-lg text-muted-foreground">
          Learn how to use the DDU CSC Grasshopper components to work with the Catalogue of Second Chances.
        </p>
      </div>

      <div className="space-y-4">
        {sections.map((section) => {
          const Icon = section.icon
          const isExpanded = expandedSection === section.id
          
          return (
            <div key={section.id} className="border rounded-lg">
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
          <li>• Ensure you're properly authenticated with CSC_SignIn</li>
          <li>• Verify your internet connection for API access</li>
          <li>• Contact the DDU team through the main website</li>
        </ul>
      </div>
    </div>
  )
}