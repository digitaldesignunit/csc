#!/usr/bin/env tsx

/**
 * Writes the example records of the "Data Model" page (`lib/dataModelExamples.ts`)
 * as JSON to `tests/fixtures/data_model_examples.json`, so that a backend test
 * can check every one of them against the backend models (decision 8.181).
 * A frontend test fails when the file is out of date: run
 *
 *     npx tsx scripts/export-data-model-examples.ts
 *
 * from `src/frontend` after a change of the examples.
 */
import fs from 'fs'
import path from 'path'

import { EXAMPLE_RECORDS } from '../lib/dataModelExamples'
import { exampleExport } from '../lib/dataModelExport'

const target = path.join(process.cwd(), '..', '..', 'tests', 'fixtures', 'data_model_examples.json')
fs.writeFileSync(target, exampleExport(EXAMPLE_RECORDS))
console.log(`Wrote ${target}`)
