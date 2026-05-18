#!/usr/bin/env tsx

/**
 * Generates TypeScript from FastAPI `model_json_schema()` JSON.
 *
 * All schemas are fetched from `FASTAPI_URL` (override with env when generating
 * against a local backend), e.g. `FASTAPI_URL=http://127.0.0.1:8000 npm run generate:models`.
 *
 * - `/schema/component` → `ComponentModel` (legacy document; designs, etc.)
 * - `/schema/design` → `DesignModel`
 * - `/schema/catalog-compose` → `CatalogModels` (v0.5 `GET /identities/{id}/compose` body)
 */

import fs from 'fs'
import path from 'path'

const BACKEND_URL = process.env.FASTAPI_URL || 'https://api.ddu.uber.space'
const OUTPUT_DIR = path.join(process.cwd(), 'generated')

/** Reuse legacy `ComponentModel.ts` defs to avoid duplicate exports from `index.ts`. */
const CATALOG_DEFS_FROM_COMPONENT_MODEL = new Set([
  'ComponentBoundingBox',
  'ComponentFrame',
  'ComponentLocation',
])

async function generateModel(
  schemaPath: string,
  interfaceName: string,
  outputFileName: string,
  options?: { catalogCompose?: boolean },
) {
  const catalogCompose = options?.catalogCompose ?? false
  console.log(`🔍 Fetching ${interfaceName} schema from ${BACKEND_URL}${schemaPath}...`)
  const response = await fetch(`${BACKEND_URL}${schemaPath}`)
  if (!response.ok) {
    throw new Error(
      `Failed to fetch schema (${interfaceName}): ${response.status} ${response.statusText}`,
    )
  }
  const schema = await response.json()
  console.log(`✅ ${interfaceName} schema fetched successfully`)
  writeGeneratedModel(schema, interfaceName, schemaPath, outputFileName, {
    catalogCompose,
  })
}

function writeGeneratedModel(
  schema: Record<string, unknown>,
  rootInterfaceName: string,
  schemaPath: string,
  outputFileName: string,
  opts: { catalogCompose: boolean },
) {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true })
    console.log('📁 Created output directory')
  }

  const typescriptCode = generateTypeScriptInterface(
    schema,
    rootInterfaceName,
    schemaPath,
    opts,
  )
  const outFile = path.join(OUTPUT_DIR, outputFileName)
  fs.writeFileSync(outFile, typescriptCode)
  console.log(`📝 Generated TypeScript model: ${outFile}`)
}

async function run() {
  try {
    await generateModel('/schema/component', 'ComponentModel', 'ComponentModel.ts')

    await generateModel('/schema/design', 'DesignModel', 'DesignModel.ts')

    await generateModel('/schema/catalog-compose', 'ComposeIdentityResponse', 'CatalogModels.ts', {
      catalogCompose: true,
    })

    const indexFile = path.join(OUTPUT_DIR, 'index.ts')
    const indexContent = `// Auto-generated models from backend OpenAPI schema
export * from './ComponentModel';
export * from './DesignModel';
export * from './CatalogModels';
export * from './catalogExtras';
`
    fs.writeFileSync(indexFile, indexContent)
    console.log(`📝 Updated index file: ${indexFile}`)

    console.log('🎉 Model generation completed successfully!')
  } catch (error) {
    console.error('❌ Error generating models:', error)
    process.exit(1)
  }
}

type Schema = Record<string, unknown> & {
  $ref?: string
  type?: string
  enum?: unknown[]
  items?: Schema
  properties?: Record<string, Schema>
  required?: string[]
  anyOf?: Schema[]
  oneOf?: Schema[]
  allOf?: Schema[]
}

const SHARED_COMPONENT_DEFS = new Set([
  'ComponentExtrusion',
  'ComponentGeometry',
  'ComponentMesh',
  'ComponentMeshColors',
  'ComponentMeshFaces',
  'ComponentMeshVertices',
  'ComponentPolylinePoints',
])

function generateTypeScriptInterface(
  schema: Record<string, unknown>,
  rootInterfaceName: string,
  schemaPath: string,
  opts: { catalogCompose: boolean },
): string {
  const { properties, required = [], $defs } = schema as {
    properties: Record<string, unknown>
    required?: string[]
    $defs?: Record<string, unknown>
  }

  let interfaceCode = `// Auto-generated from backend OpenAPI schema
// Generated on: ${new Date().toISOString()}
// Source: ${BACKEND_URL}${schemaPath}
`

  if (rootInterfaceName === 'DesignModel') {
    interfaceCode += `
import { ComponentGeometry } from './ComponentModel';
`
  }

  if (opts.catalogCompose) {
    interfaceCode += `
import type {
  ComponentBoundingBox,
  ComponentFrame,
  ComponentLocation,
} from './ComponentModel';
`
  }

  interfaceCode += `
`

  if ($defs) {
    for (const [defName, defSchema] of Object.entries($defs)) {
      if (rootInterfaceName === 'DesignModel' && SHARED_COMPONENT_DEFS.has(defName)) {
        continue
      }
      if (opts.catalogCompose && CATALOG_DEFS_FROM_COMPONENT_MODEL.has(defName)) {
        continue
      }
      interfaceCode += generateNestedInterface(
        defName,
        defSchema as Record<string, unknown>,
        $defs,
        opts,
      )
      interfaceCode += '\n\n'
    }
  }

  interfaceCode += `export interface ${rootInterfaceName} {\n`

  for (const [propName, propSchema] of Object.entries(properties)) {
    const isRequired = (required as string[]).includes(propName)
    const typeAnnotation = getTypeScriptType(propSchema as Schema, $defs, opts)
    const comment = (propSchema as Record<string, unknown>).description
      ? ` // ${(propSchema as Record<string, unknown>).description}`
      : ''

    interfaceCode += `  ${propName}${isRequired ? '' : '?'}: ${typeAnnotation};${comment}\n`
  }

  interfaceCode += '}\n\n'

  if (rootInterfaceName === 'ComponentModel') {
    interfaceCode += `// Utility types for better type safety
export type ComponentType =
  | 'panel'
  | 'beam'
  | 'column'
  | 'slab'
  | 'rubble'
  | 'brick'
  | 'pipe'
  | 'profile'
  | 'connector'
  | 'other';
export type ComponentComplexity = 0 | 1 | 2 | 3;
export type ComponentCondition = 0 | 1 | 2 | 3;
export type ComponentManufacturedPrecision = 'exact' | 'month' | 'year' | 'unknown';

// Type guards
export function isComponentModel(obj: unknown): obj is ComponentModel {
  return obj !== null && 
         typeof obj === 'object' && 
         '_id' in obj && 
         'type' in obj;
}

// Extension types
export interface ExtendedComponentModel extends ComponentModel {
  reserved_by_username?: string;
  /** Current snapshot \`_id\` (v0.5); used for \`/snapshots/{id}/preview\` thumbnails */
  current_snapshot_id?: string;
  catalog_number?: number;
  consumed_at?: string | null;
  parent_identities?: string[];
}

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
`
  }

  if (opts.catalogCompose && rootInterfaceName === 'ComposeIdentityResponse') {
    interfaceCode += `/** Canonical read model: \`GET /identities/{id}/compose\` (same JSON as the API). */
export type CatalogComponent = ComposeIdentityResponse

`
  }

  return interfaceCode
}

function generateNestedInterface(
  name: string,
  schema: Record<string, unknown>,
  $defs: Record<string, unknown> | undefined,
  genOpts: { catalogCompose: boolean },
): string {
  const { properties, required = [] } = schema as {
    properties?: Record<string, unknown>
    required?: string[]
  }

  if (!properties) {
    const typeAnnotation = getTypeScriptType(schema as Schema, $defs, genOpts)
    return `export type ${name} = ${typeAnnotation};\n`
  }

  let interfaceCode = `export interface ${name} {\n`

  for (const [propName, propSchema] of Object.entries(properties)) {
    const isRequired = (required as string[]).includes(propName)
    const typeAnnotation = getTypeScriptType(propSchema as Schema, $defs, genOpts)
    const comment = (propSchema as Record<string, unknown>).description
      ? ` // ${(propSchema as Record<string, unknown>).description}`
      : ''

    interfaceCode += `  ${propName}${isRequired ? '' : '?'}: ${typeAnnotation};${comment}\n`
  }

  interfaceCode += '}'
  return interfaceCode
}

function getTypeScriptType(
  schema: Schema,
  $defs: Record<string, unknown> | undefined,
  genOpts: { catalogCompose: boolean },
): string {
  const catalogCompose = genOpts.catalogCompose
  if (schema.$ref && typeof schema.$ref === 'string') {
    const refPath = schema.$ref
    if (refPath.startsWith('#/$defs/')) {
      const refName = refPath.replace('#/$defs/', '')
      if (catalogCompose && CATALOG_DEFS_FROM_COMPONENT_MODEL.has(refName)) {
        return refName
      }
      return refName
    }
  }

  if (schema.type === 'string') {
    if (Array.isArray(schema.enum)) {
      return (schema.enum as unknown[])
        .map((v: unknown) => `'${String(v)}'`)
        .join(' | ')
    }
    return 'string'
  }

  if (schema.type === 'integer' || schema.type === 'number') {
    if (Array.isArray(schema.enum)) {
      return (schema.enum as unknown[]).map((v) => String(v)).join(' | ')
    }
    return 'number'
  }

  if (schema.type === 'boolean') {
    return 'boolean'
  }

  if (schema.type === 'array') {
    const itemType = getTypeScriptType((schema.items as Schema) ?? {}, $defs, genOpts)
    return `${itemType}[]`
  }

  if (schema.type === 'object') {
    if (schema.properties && typeof schema.properties === 'object') {
      return generateNestedInterface(
        'Anonymous',
        { properties: schema.properties, required: schema.required } as unknown as Record<
          string,
          unknown
        >,
        $defs,
        genOpts,
      )
    }
    return 'Record<string, unknown>'
  }

  if (Array.isArray(schema.anyOf)) {
    const types = (schema.anyOf as Schema[]).map((s: Schema) =>
      getTypeScriptType(s, $defs, genOpts),
    )
    const filtered = types.filter((t: string) => t !== 'any')
    if (filtered.length === 0) return 'unknown'
    if (filtered.length === 1) return filtered[0]
    return filtered.join(' | ')
  }

  if (Array.isArray(schema.oneOf)) {
    const types = (schema.oneOf as Schema[]).map((s: Schema) =>
      getTypeScriptType(s, $defs, genOpts),
    )
    const filtered = types.filter((t: string) => t !== 'any')
    if (filtered.length === 0) return 'unknown'
    if (filtered.length === 1) return filtered[0]
    return filtered.join(' | ')
  }

  if (Array.isArray(schema.allOf)) {
    const types = (schema.allOf as Schema[]).map((s: Schema) =>
      getTypeScriptType(s, $defs, genOpts),
    )
    const filtered = types.filter((t: string) => t !== 'any')
    if (filtered.length === 0) return 'unknown'
    if (filtered.length === 1) return filtered[0]
    return filtered.join(' & ')
  }

  return 'unknown'
}

run().catch((error) => {
  console.error('💥 Model generation failed:', error)
  process.exit(1)
})
