import type { Origin } from '@/generated/CatalogModels'
import type { OriginalFunction } from '@/generated/Vocab'
import type { SnapshotFields } from '@/lib/snapshotForm'

/** Everything the snapshot form collects, across its steps. */
export type FormValues = {
  /** The id on the new tag (new: required; cut: empty = generated). */
  tag: string
  parents: string[]
  dataset: string
  originalFunction: OriginalFunction | null
  material: string
  tradeName: string
  /** New component only; null = not stated here (edited later). */
  origin: Origin | null
  fields: SnapshotFields
  dims: [string, string, string]
  /** Correct: the geometry is kept unless a size is entered again; a draw
   *  from a batch takes the batch's proxy unless a size is entered. */
  sizeEntered: boolean
  photos: File[]
  /** New component: record a visual inspection next (the evidence form). */
  inspect: boolean
}
