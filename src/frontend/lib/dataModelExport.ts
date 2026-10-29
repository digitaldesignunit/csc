/**
 * The example records of the "Data Model" page as the JSON file the backend
 * test reads (`tests/fixtures/data_model_examples.json`): the id, the model
 * the record belongs to and the record itself, no comments.
 */
import type { ExampleRecord } from '@/lib/dataModelExamples'

export function exampleExport(records: ExampleRecord[]): string {
  const out = records.map((record) => ({ id: record.id, model: record.model, json: record.json }))
  return `${JSON.stringify(out, null, 2)}\n`
}
