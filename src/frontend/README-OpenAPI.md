# OpenAPI Model Generation

This project uses OpenAPI schema generation to keep frontend TypeScript models in sync with backend Pydantic models.

## How It Works

1. **Backend**: Pydantic models are enhanced with OpenAPI documentation and Field descriptions
2. **Schema Endpoint**: `/schema/component` endpoint exposes the ComponentModel schema
3. **Frontend Generation**: Script fetches schema and generates TypeScript interfaces
4. **Auto-sync**: Models are automatically kept in sync

## Usage

### Generate Models

```bash
# Generate ComponentModel from backend
npm run generate:models
```

### Development Workflow

1. **Update Backend Model**: Modify Pydantic model in `src/backend/apps/catalogue/models.py`
2. **Restart Backend**: Restart FastAPI to regenerate OpenAPI schema
3. **Generate Frontend Models**: Run `npm run generate:models`
4. **Use Generated Models**: Import from `src/generated/ComponentModel`

### Import Generated Models

```typescript
// Instead of importing from components/common/models
// import { ComponentData } from '@/components/common/models';

// Import from generated models
import { ComponentModel, ComponentType, ComponentComplexity } from '@/generated/ComponentModel';

// Use the generated interface
const component: ComponentModel = {
  _id: "uuid",
  type: "slab",
  material: "concrete",
  // ... other properties
};
```

## File Structure

```
src/frontend/
├── scripts/
│   └── generate-models.ts    # Generation script
├── generated/                 # Auto-generated models
│   ├── ComponentModel.ts     # Generated ComponentModel interface
│   └── index.ts             # Export index
└── package.json              # Contains generate:models script
```

## Configuration

### Environment Variables

- `BACKEND_URL`: Backend API URL (defaults to `http://localhost:8000`)

### Script Options

The generation script automatically:
- Fetches schema from `/schema/component` endpoint
- Generates TypeScript interfaces with proper types
- Adds utility types and type guards
- Creates index files for easy imports
- Handles required/optional properties
- Preserves field descriptions as comments

## Benefits

1. **Single Source of Truth**: Backend Pydantic models are the authoritative source
2. **Type Safety**: Frontend always has correct types matching backend
3. **Automated Sync**: No manual type copying required
4. **Documentation**: Field descriptions are preserved in generated code
5. **Validation**: Type guards help with runtime validation

## Migration Path

To migrate existing code:

1. **Generate new models**: `npm run generate:models`
2. **Update imports**: Change from `@/components/common/models` to `@/generated/ComponentModel`
3. **Update type names**: Change `ComponentData` to `ComponentModel`
4. **Test thoroughly**: Ensure all components still work correctly

## Troubleshooting

### Schema Fetch Fails
- Ensure backend is running on `BACKEND_URL`
- Check `/schema/component` endpoint is accessible
- Verify backend has the schema endpoint

### Type Mismatches
- Regenerate models after backend changes
- Check that backend model changes are deployed
- Verify OpenAPI schema is up-to-date

### Build Errors
- Ensure generated models are committed to git
- Check that generation script runs successfully
- Verify TypeScript compilation passes
