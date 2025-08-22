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

function generateTypeScriptInterface(schema: any): string {
  const { properties, required = [] } = schema;
  
  let interfaceCode = `// Auto-generated from backend OpenAPI schema
// Generated on: ${new Date().toISOString()}
// Source: ${BACKEND_URL}/schema/component

export interface ComponentModel {
`;

  // Add properties
  for (const [propName, propSchema] of Object.entries(properties) as [string, any][]) {
    const isRequired = required.includes(propName);
    const typeAnnotation = getTypeScriptType(propSchema);
    const comment = propSchema.description ? ` // ${propSchema.description}` : '';
    
    interfaceCode += `  ${propName}${isRequired ? '' : '?'}: ${typeAnnotation};${comment}\n`;
  }
  
  interfaceCode += '}\n\n';
  
  // Add utility types for better type safety
  interfaceCode += `// Utility types for better type safety
export type ComponentType = 'sheet' | 'beam' | 'slab' | 'rubble' | 'column';
export type ComponentComplexity = 0 | 1 | 2 | 3;

// Type guards
export function isComponentModel(obj: any): obj is ComponentModel {
  return obj && typeof obj === 'object' && '_id' in obj && 'type' in obj;
}

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
`;
  
  return interfaceCode;
}

function getTypeScriptType(schema: any): string {
  if (schema.type === 'string') {
    if (schema.enum) {
      return schema.enum.map((v: any) => `'${v}'`).join(' | ');
    }
    return 'string';
  }
  
  if (schema.type === 'integer' || schema.type === 'number') {
    if (schema.enum) {
      return schema.enum.join(' | ');
    }
    return 'number';
  }
  
  if (schema.type === 'boolean') {
    return 'boolean';
  }
  
  if (schema.type === 'array') {
    const itemType = getTypeScriptType(schema.items);
    return `${itemType}[]`;
  }
  
  if (schema.type === 'object') {
    return 'Record<string, any>';
  }
  
  // Handle anyOf, oneOf, allOf
  if (schema.anyOf) {
    return schema.anyOf.map((s: any) => getTypeScriptType(s)).join(' | ');
  }
  
  if (schema.oneOf) {
    return schema.oneOf.map((s: any) => getTypeScriptType(s)).join(' | ');
  }
  
  if (schema.allOf) {
    return schema.allOf.map((s: any) => getTypeScriptType(s)).join(' & ');
  }
  
  // Default fallback
  return 'any';
}

// Run the generation
generateComponentModel().then(() => {
  console.log('🎉 Model generation completed successfully!');
}).catch((error) => {
  console.error('💥 Model generation failed:', error);
  process.exit(1);
});
