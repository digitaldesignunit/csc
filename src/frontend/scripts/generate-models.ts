#!/usr/bin/env tsx

import fs from 'fs';
import path from 'path';

const BACKEND_URL = process.env.FASTAPI_URL || 'https://api.ddu.uber.space';
const OUTPUT_DIR = path.join(process.cwd(), 'generated');

async function generateModel(
  schemaPath: string,
  interfaceName: string,
  outputFileName: string
) {
  console.log(`🔍 Fetching ${interfaceName} schema from backend...`);
  const response = await fetch(`${BACKEND_URL}${schemaPath}`);
  if (!response.ok) {
    throw new Error(
      `Failed to fetch schema (${interfaceName}): ${response.status} ${response.statusText}`
    );
  }
  const schema = await response.json();
  console.log(`✅ ${interfaceName} schema fetched successfully`);

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    console.log('📁 Created output directory');
  }

  const typescriptCode = generateTypeScriptInterface(schema, interfaceName, schemaPath);
  const outFile = path.join(OUTPUT_DIR, outputFileName);
  fs.writeFileSync(outFile, typescriptCode);
  console.log(`📝 Generated TypeScript model: ${outFile}`);
}

async function run() {
  try {
    // Component model
    await generateModel('/schema/component', 'ComponentModel', 'ComponentModel.ts');

    // Design model
    await generateModel('/schema/design', 'DesignModel', 'DesignModel.ts');

    // Create/update index file
    const indexFile = path.join(OUTPUT_DIR, 'index.ts');
    const indexContent = `// Auto-generated models from backend OpenAPI schema
export * from './ComponentModel';
export * from './DesignModel';
`;
    fs.writeFileSync(indexFile, indexContent);
    console.log(`📝 Updated index file: ${indexFile}`);

    console.log('🎉 Model generation completed successfully!');
  } catch (error) {
    console.error('❌ Error generating models:', error);
    process.exit(1);
  }
}

function generateTypeScriptInterface(
  schema: Record<string, unknown>,
  rootInterfaceName: string,
  schemaPath: string
): string {
  const { properties, required = [], $defs } = schema as {
    properties: Record<string, unknown>;
    required?: string[];
    $defs?: Record<string, unknown>;
  };

  let interfaceCode = `// Auto-generated from backend OpenAPI schema
// Generated on: ${new Date().toISOString()}
// Source: ${BACKEND_URL}${schemaPath}

`;

  // Generate nested interfaces first
  if ($defs) {
    for (const [defName, defSchema] of Object.entries($defs)) {
      interfaceCode += generateNestedInterface(defName, defSchema as Record<string, unknown>, $defs);
      interfaceCode += '\n\n';
    }
  }

  interfaceCode += `export interface ${rootInterfaceName} {\n`;

  // Add properties
  for (const [propName, propSchema] of Object.entries(properties)) {
    const isRequired = required.includes(propName);
    const typeAnnotation = getTypeScriptType(propSchema as Record<string, unknown>, $defs);
    const comment = (propSchema as Record<string, unknown>).description ? ` // ${(propSchema as Record<string, unknown>).description}` : '';

    interfaceCode += `  ${propName}${isRequired ? '' : '?'}: ${typeAnnotation};${comment}\n`;
  }

  interfaceCode += '}\n\n';

  if (rootInterfaceName === 'ComponentModel') {
    interfaceCode += `// Utility types for better type safety
export type ComponentType = 'sheet' | 'beam' | 'slab' | 'rubble' | 'column';
export type ComponentComplexity = 0 | 1 | 2 | 3;

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
}

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
`;
  }

  return interfaceCode;
}

function generateNestedInterface(name: string, schema: Record<string, unknown>, $defs?: Record<string, unknown>): string {
  const { properties, required = [] } = schema as { properties?: Record<string, unknown>; required?: string[] };

  // Handle RootModel types (like ComponentBoundingBox) that don't have properties
  if (!properties) {
    const typeAnnotation = getTypeScriptType(schema, $defs);
    return `export type ${name} = ${typeAnnotation};\n`;
  }

  let interfaceCode = `export interface ${name} {\n`;

  for (const [propName, propSchema] of Object.entries(properties)) {
    const isRequired = required.includes(propName);
    const typeAnnotation = getTypeScriptType(propSchema as Record<string, unknown>, $defs);
    const comment = (propSchema as Record<string, unknown>).description ? ` // ${(propSchema as Record<string, unknown>).description}` : '';

    interfaceCode += `  ${propName}${isRequired ? '' : '?'}: ${typeAnnotation};${comment}\n`;
  }

  interfaceCode += '}';
  return interfaceCode;
}

function getTypeScriptType(schema: Record<string, unknown>, $defs?: Record<string, unknown>): string {
  // Handle $ref references
  if ((schema as any).$ref) {
    const refPath = (schema as any).$ref as string;
    if (refPath.startsWith('#/$defs/')) {
      const refName = refPath.replace('#/$defs/', '');
      return refName;
    }
  }

  if ((schema as any).type === 'string') {
    if ((schema as any).enum) {
      return ((schema as any).enum as unknown[]).map((v: unknown) => `'${v}'`).join(' | ');
    }
    return 'string';
  }

  if ((schema as any).type === 'integer' || (schema as any).type === 'number') {
    if ((schema as any).enum) {
      return ((schema as any).enum as unknown[]).join(' | ');
    }
    return 'number';
  }

  if ((schema as any).type === 'boolean') {
    return 'boolean';
  }

  if ((schema as any).type === 'array') {
    const itemType = getTypeScriptType(((schema as any).items as Record<string, unknown>), $defs);
    return `${itemType}[]`;
  }

  if ((schema as any).type === 'object') {
    // Check if this is a specific nested type with properties
    if ((schema as any).properties) {
      return generateNestedInterface('Anonymous', (schema as any) as { properties: Record<string, unknown>; required?: string[] });
    }
    return 'Record<string, unknown>';
  }

  // Handle anyOf, oneOf, allOf
  if ((schema as any).anyOf) {
    const types = (((schema as any).anyOf as Record<string, unknown>[])).map((s: Record<string, unknown>) => getTypeScriptType(s, $defs));
    const filteredTypes = (types as string[]).filter((t: string) => t !== 'any');
    if (filteredTypes.length === 0) return 'unknown';
    if (filteredTypes.length === 1) return filteredTypes[0];
    return filteredTypes.join(' | ');
  }

  if ((schema as any).oneOf) {
    const types = (((schema as any).oneOf as Record<string, unknown>[])).map((s: Record<string, unknown>) => getTypeScriptType(s, $defs));
    const filteredTypes = (types as string[]).filter((t: string) => t !== 'any');
    if (filteredTypes.length === 0) return 'unknown';
    if (filteredTypes.length === 1) return filteredTypes[0];
    return filteredTypes.join(' | ');
  }

  if ((schema as any).allOf) {
    const types = (((schema as any).allOf as Record<string, unknown>[])).map((s: Record<string, unknown>) => getTypeScriptType(s, $defs));
    const filteredTypes = (types as string[]).filter((t: string) => t !== 'any');
    if (filteredTypes.length === 0) return 'unknown';
    if (filteredTypes.length === 1) return filteredTypes[0];
    return filteredTypes.join(' & ');
  }

  // Default fallback - use 'unknown' instead of 'any'
  return 'unknown';
}

// Run the generation
run().catch((error) => {
  console.error('💥 Model generation failed:', error);
  process.exit(1);
});
