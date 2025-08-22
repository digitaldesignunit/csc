# Migration Guide: Old Models → Generated Models

This guide helps you migrate from the old `ComponentData` type to the new generated `ComponentModel` type.

## Quick Migration

### 1. **Update Imports**
```typescript
// OLD
import { ComponentData } from '@/components/common/models';

// NEW
import { ComponentModel } from '@/generated/ComponentModel';
```

### 2. **Update Type Names**
```typescript
// OLD
const component: ComponentData = { ... };

// NEW
const component: ComponentModel = { ... };
```

### 3. **Update Function Signatures**
```typescript
// OLD
function processComponent(component: ComponentData) { ... }

// NEW
function processComponent(component: ComponentModel) { ... }
```

## Detailed Changes

### **Property Mapping**

| Old Property | New Property | Notes |
|--------------|--------------|-------|
| `_id` | `_id` | ✅ Same |
| `type` | `type` | ✅ Same |
| `material` | `material` | ✅ Same |
| `complexity` | `complexity` | ✅ Same |
| `fragment` | `fragment` | ✅ Same |
| `assembly` | `assembly` | ✅ Same |
| `color` | `color` | ✅ Same |
| `geometry` | `geometry` | ✅ Same |
| `validated` | `validated` | ✅ Same |
| `bbx` | `bbx` | ✅ Same |
| `location` | `location` | ✅ Same |
| `descriptors` | `descriptors` | ✅ Same |
| `processes` | `processes` | ✅ Same |
| `attributes` | `attributes` | ✅ Same |
| `iframe` | `iframe` | ✅ Same |
| `name` | `name` | ✅ Same |
| `created` | `created` | ✅ Same |
| `lastmodified` | `lastmodified` | ✅ Same |

### **Type Improvements**

The new generated model provides better type safety:

```typescript
// OLD: Generic types
export type ComponentBoundingBox = Array<Array<number>>
export type ComponentLocation = { lat: number, lon: number }

// NEW: Generated from backend schema
// All types are automatically inferred from Pydantic model
// Better validation and documentation
```

## Migration Steps

### **Step 1: Generate New Models**
```bash
# Make sure backend is running
npm run generate:models
```

### **Step 2: Update One Component at a Time**
Start with a simple component and work your way up:

```typescript
// Example: ComponentDetailCard.tsx
import { ComponentModel } from '@/generated/ComponentModel';

export default function ComponentDetailCard({
  component_data,
}: {
  component_data: ComponentModel  // ← Changed from ComponentData
}) {
  // ... rest of component
}
```

### **Step 3: Test Each Change**
After each file update:
1. Check TypeScript compilation
2. Test the component in browser
3. Verify no runtime errors

### **Step 4: Remove Old Imports**
Once all components are migrated:
1. Remove unused imports from `@/components/common/models`
2. Consider removing the old models file if no longer needed

## Benefits of Migration

1. **Single Source of Truth**: Backend Pydantic model is authoritative
2. **Automatic Sync**: No manual type copying required
3. **Better Documentation**: Field descriptions preserved in generated code
4. **Type Safety**: Exact match with backend types
5. **Future Proof**: Changes to backend automatically update frontend

## Troubleshooting

### **Type Mismatches**
If you see type errors:
1. Regenerate models: `npm run generate:models`
2. Check backend model changes
3. Verify OpenAPI schema is up-to-date

### **Missing Properties**
If properties are missing:
1. Check backend Pydantic model
2. Ensure Field descriptions are added
3. Regenerate models

### **Build Errors**
If build fails:
1. Check generated models exist
2. Verify TypeScript compilation
3. Check import paths are correct

## Rollback Plan

If you need to rollback:
1. Revert import changes
2. Use old `ComponentData` type
3. Remove generated models directory
4. Continue with manual type management

## Support

For issues with the migration:
1. Check the generated `ComponentModel.ts` file
2. Verify backend schema endpoint works
3. Review OpenAPI documentation
4. Check backend logs for errors
