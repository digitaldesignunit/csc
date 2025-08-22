#!/usr/bin/env tsx

import fs from 'fs';
import path from 'path';

const BACKEND_URL = process.env.FASTAPI_URL || 'https://api.ddu.uber.space';
const OUTPUT_DIR = path.join(process.cwd(), 'src', 'generated');
const MODELS_FILE = path.join(OUTPUT_DIR, 'ComponentModel.ts');

async function generateComponentModel() {
  try {
    console.log('🔍 Fetching ComponentModel schema from backend...');
    
    // Fetch the schema from our backend endpoint
    const response = await fetch(`${BACKEND_URL}/schema/component`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch schema: ${response.status} ${response.statusText}`);
    }
    
    const schema = await response.json();
    console.log('✅ Schema fetched successfully');
    
    // Create output directory if it doesn't exist
    if (!fs.existsSync(OUTPUT_DIR)) {
      fs.mkdirSync(OUTPUT_DIR, { recursive: true });
      console.log('📁 Created output directory');
    }
    
    // Generate TypeScript interface
    const typescriptCode = generateTypeScriptInterface(schema);
    
    // Write to file
    fs.writeFileSync(MODELS_FILE, typescriptCode);
    console.log(`📝 Generated TypeScript model: ${MODELS_FILE}`);
    
    // Also create an index file for easy imports
    const indexFile = path.join(OUTPUT_DIR, 'index.ts');
    const indexContent = `// Auto-generated models from backend OpenAPI schema
export * from './ComponentModel';
`;
    fs.writeFileSync(indexFile, indexContent);
    console.log(`📝 Created index file: ${indexFile}`);
    
  } catch (error) {
    console.error('❌ Error generating models:', error);
    process.exit(1);
  }
}

function generateTypeScriptInterface(schema: Record<string, unknown>): string {
  const { properties, required = [] } = schema as { properties: Record<string, unknown>; required?: string[] };
  
  let interfaceCode = `// Auto-generated from backend OpenAPI schema
// Generated on: ${new Date().toISOString()}
// Source: ${BACKEND_URL}/schema/component

export interface ComponentModel {
`;

  // Add properties
  for (const [propName, propSchema] of Object.entries(properties)) {
    const isRequired = required.includes(propName);
    const typeAnnotation = getTypeScriptType(propSchema as Record<string, unknown>);
    const comment = (propSchema as Record<string, unknown>).description ? ` // ${(propSchema as Record<string, unknown>).description}` : '';
    
    interfaceCode += `  ${propName}${isRequired ? '' : '?'}: ${typeAnnotation};${comment}\n`;
  }
  
  interfaceCode += '}\n\n';
  
  // Add utility types for better type safety
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

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
`;
  
  return interfaceCode;
}

function getTypeScriptType(schema: Record<string, unknown>): string {
  if (schema.type === 'string') {
    if (schema.enum) {
      return (schema.enum as unknown[]).map((v: unknown) => `'${v}'`).join(' | ');
    }
    return 'string';
  }
  
  if (schema.type === 'integer' || schema.type === 'number') {
    if (schema.enum) {
      return (schema.enum as unknown[]).join(' | ');
    }
    return 'number';
  }
  
  if (schema.type === 'boolean') {
    return 'boolean';
  }
  
  if (schema.type === 'array') {
    const itemType = getTypeScriptType(schema.items as Record<string, unknown>);
    return `${itemType}[]`;
  }
  
  if (schema.type === 'object') {
    return 'Record<string, unknown>';
  }
  
  // Handle anyOf, oneOf, allOf
  if (schema.anyOf) {
    const types = (schema.anyOf as Record<string, unknown>[]).map((s: Record<string, unknown>) => getTypeScriptType(s));
    // Filter out 'any' types to avoid union with any
    const filteredTypes = types.filter((t: string) => t !== 'any');
    if (filteredTypes.length === 0) return 'unknown';
    if (filteredTypes.length === 1) return filteredTypes[0];
    return filteredTypes.join(' | ');
  }
  
  if (schema.oneOf) {
    const types = (schema.oneOf as Record<string, unknown>[]).map((s: Record<string, unknown>) => getTypeScriptType(s));
    // Filter out 'any' types to avoid union with any
    const filteredTypes = types.filter((t: string) => t !== 'any');
    if (filteredTypes.length === 0) return 'unknown';
    if (filteredTypes.length === 1) return filteredTypes[0];
    return filteredTypes.join(' | ');
  }
  
  if (schema.allOf) {
    const types = (schema.allOf as Record<string, unknown>[]).map((s: Record<string, unknown>) => getTypeScriptType(s));
    // Filter out 'any' types to avoid intersection with any
    const filteredTypes = types.filter((t: string) => t !== 'any');
    if (filteredTypes.length === 0) return 'unknown';
    if (filteredTypes.length === 1) return filteredTypes[0];
    return filteredTypes.join(' & ');
  }
  
  // Default fallback - use 'unknown' instead of 'any'
  return 'unknown';
}

// Run the generation
generateComponentModel().then(() => {
  console.log('🎉 Model generation completed successfully!');
}).catch((error) => {
  console.error('💥 Model generation failed:', error);
  process.exit(1);
});
