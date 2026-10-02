#!/usr/bin/env tsx

/**
 * Generates TypeScript from FastAPI `model_json_schema()` JSON.
 *
 * All schemas are fetched from `FASTAPI_URL` (override with env when generating
 * against a local backend), e.g. `FASTAPI_URL=http://127.0.0.1:8000 npm run generate:models`.
 *
 * - `/schema/catalog-shared` --> `CatalogSharedTypes.ts` (frames, location, mesh types)
 * - `/schema/catalog-compose` --> `CatalogModels` (passport body with snapshots[])
 * - `/schema/catalog-row` --> `CatalogRow` in `CatalogModels.ts` (list rows)
 * - `/schema/snapshot-summary` --> `SnapshotSummaryItem` in `SnapshotModels.ts`
 * - `/schema/pending-snapshot` --> `PendingSnapshotItem` in `SnapshotModels.ts`
 * - `/schema/access` --> `AccessModels.ts` (me, datasets, invitations, users, tombstones)
 */

import fs from 'fs'
import path from 'path'

const BACKEND_URL = process.env.FASTAPI_URL || 'https://api.2ndchances.build'
const OUTPUT_DIR = path.join(process.cwd(), 'generated')

/**
 * Defs generated into `CatalogSharedTypes.ts`; the passport output imports
 * them instead of repeating them. Filled while generating the shared file.
 */
const SHARED_DEFS_FROM_CATALOG_SHARED = new Set<string>()

async function generateModel(
  schemaPath: string,
  interfaceName: string,
  outputFileName: string,
  options?: { catalogPassport?: boolean; defsOnly?: boolean },
) {
  const catalogPassport = options?.catalogPassport ?? false
  const defsOnly = options?.defsOnly ?? false
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
    catalogPassport,
    defsOnly,
  })
}

function writeGeneratedModel(
  schema: Record<string, unknown>,
  rootInterfaceName: string,
  schemaPath: string,
  outputFileName: string,
  opts: { catalogPassport: boolean; defsOnly: boolean },
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

async function appendModelFromSchema(
  schemaPath: string,
  interfaceName: string,
  outputFileName: string,
) {
  console.log(`🔍 Fetching ${interfaceName} schema from ${BACKEND_URL}${schemaPath}...`)
  const response = await fetch(`${BACKEND_URL}${schemaPath}`)
  if (!response.ok) {
    throw new Error(
      `Failed to fetch schema (${interfaceName}): ${response.status} ${response.statusText}`,
    )
  }
  const schema = await response.json()
  console.log(`✅ ${interfaceName} schema fetched successfully`)

  const outFile = path.join(OUTPUT_DIR, outputFileName)
  const typescriptBlock = generateTypeScriptInterface(
    schema,
    interfaceName,
    schemaPath,
    { catalogPassport: false, defsOnly: false },
  )
  // only the root interface: its defs already live in the file appended to
  const rootStart = typescriptBlock.indexOf(`export interface ${interfaceName} {`)
  const interfaceOnly = typescriptBlock.slice(rootStart)
  fs.appendFileSync(outFile, `\n${interfaceOnly}`)
  console.log(`📝 Appended ${interfaceName} to ${outFile}`)
}

async function run() {
  try {
    await generateModel(
      '/schema/catalog-shared',
      'CatalogSharedTypesEnvelope',
      'CatalogSharedTypes.ts',
      { defsOnly: true },
    )

    await generateModel('/schema/catalog-compose', 'ComponentPassport', 'CatalogModels.ts', {
      catalogPassport: true,
    })

    await appendModelFromSchema('/schema/catalog-row', 'CatalogRow', 'CatalogModels.ts')

    await generateModel(
      '/schema/snapshot-summary',
      'SnapshotSummaryItem',
      'SnapshotModels.ts',
    )

    await appendModelFromSchema(
      '/schema/pending-snapshot',
      'PendingSnapshotItem',
      'SnapshotModels.ts',
    )

    // access, datasets, invitations, users, tombstones (plan P3)
    await generateModel('/schema/access', 'AccessTypesEnvelope', 'AccessModels.ts')

    await generateVocab()

    const indexFile = path.join(OUTPUT_DIR, 'index.ts')
    const indexContent = `// Auto-generated models from backend OpenAPI schema
export * from './CatalogSharedTypes';
export * from './CatalogModels';
export * from './SnapshotModels';
export * from './AccessModels';
export * from './Vocab';
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

const NEWLINE = String.fromCharCode(10)

/** `GET /vocab` --> `Vocab.ts`: value lists + display labels (spec section 2). */
async function generateVocab() {
  console.log(`Fetching vocabularies from ${BACKEND_URL}/vocab...`)
  const response = await fetch(`${BACKEND_URL}/vocab`)
  if (!response.ok) {
    throw new Error(`Failed to fetch /vocab: ${response.status} ${response.statusText}`)
  }
  const vocab = (await response.json()) as Record<string, { value: string; label: string }[]>
  let code = `// Auto-generated from backend GET /vocab
// Generated on: ${new Date().toISOString()}
// Source: ${BACKEND_URL}/vocab

`
  for (const [name, entries] of Object.entries(vocab)) {
    const typeName = name.replace(/(^|_)(\w)/g, (_m, _u, c: string) => c.toUpperCase())
    const values = entries.map((e) => `'${e.value}'`).join(' | ')
    const labels = entries.map((e) => `  ${JSON.stringify(e.value)}: ${JSON.stringify(e.label)},`)
    code += [
      `export type ${typeName} = ${values}`,
      `export const ${name.toUpperCase()}_LABELS: Record<${typeName}, string> = {`,
      ...labels,
      '}',
      '',
      '',
    ].join(NEWLINE)
  }
  code += `/** Display label of a vocabulary value; unknown values pass through. */
export function vocabLabel(labels: Record<string, string>, value?: string | null): string {
  if (!value) return ''
  return labels[value] ?? value
}
`
  const outFile = path.join(OUTPUT_DIR, 'Vocab.ts')
  fs.writeFileSync(outFile, code)
  console.log(`Generated ${outFile}`)
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

function generateTypeScriptInterface(
  schema: Record<string, unknown>,
  rootInterfaceName: string,
  schemaPath: string,
  opts: { catalogPassport: boolean; defsOnly: boolean },
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

  if (opts.defsOnly && $defs) {
    for (const defName of Object.keys($defs)) {
      SHARED_DEFS_FROM_CATALOG_SHARED.add(defName)
    }
  }

  // replaced by the shared-type import once the body is known (below)
  const IMPORT_SLOT = '/*__SHARED_IMPORTS__*/'
  interfaceCode += IMPORT_SLOT

  interfaceCode += `
`

  if ($defs) {
    for (const [defName, defSchema] of Object.entries($defs)) {
      if (opts.catalogPassport && SHARED_DEFS_FROM_CATALOG_SHARED.has(defName)) {
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

  if (!opts.defsOnly) {
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
  }

  if (opts.defsOnly) {
    interfaceCode += `// Shared catalog value types (frame, location, geometry, proxies)
export type ComponentComplexity = 0 | 1 | 2 | 3;
`
  }

  if (opts.catalogPassport && rootInterfaceName === 'ComponentPassport') {
    interfaceCode += `/** Canonical read model: \`GET /identities/{id}/compose\` (same JSON as the API). */
export type CatalogComponent = ComponentPassport

`
  }

  let sharedImport = ''
  if (opts.catalogPassport && $defs) {
    const body = interfaceCode.replace(IMPORT_SLOT, '')
    const shared = Object.keys($defs)
      .filter((name) => SHARED_DEFS_FROM_CATALOG_SHARED.has(name))
      .filter((name) => new RegExp(`\\b${name}\\b`).test(body))
      .sort()
    if (shared.length) {
      sharedImport = [
        '',
        'import type {',
        ...shared.map((name) => `  ${name},`),
        "} from './CatalogSharedTypes';",
        '',
      ].join(NEWLINE)
    }
  }
  return interfaceCode.replace(IMPORT_SLOT, sharedImport)
}

function generateNestedInterface(
  name: string,
  schema: Record<string, unknown>,
  $defs: Record<string, unknown> | undefined,
  genOpts: { catalogPassport: boolean; defsOnly?: boolean },
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
  genOpts: { catalogPassport: boolean },
): string {
  const catalogPassport = genOpts.catalogPassport
  if (schema.$ref && typeof schema.$ref === 'string') {
    const refPath = schema.$ref
    if (refPath.startsWith('#/$defs/')) {
      const refName = refPath.replace('#/$defs/', '')
      if (catalogPassport && SHARED_DEFS_FROM_CATALOG_SHARED.has(refName)) {
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

  if (schema.type === 'null') {
    return 'null'
  }

  if (schema.type === 'array') {
    const itemType = getTypeScriptType((schema.items as Schema) ?? {}, $defs, genOpts)
    // a union item needs parentheses: ('a' | 'b')[], not 'a' | 'b'[]
    return itemType.includes('|') ? `(${itemType})[]` : `${itemType}[]`
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
