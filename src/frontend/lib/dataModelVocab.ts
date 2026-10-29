/**
 * The vocabularies of the "Data Model" page as the backend serves them
 * (`GET /vocab`, generated into `generated/Vocab.ts`): value, label and the
 * one-line description of every value.
 */
import * as V from '@/generated/Vocab'
import { valueLabel, type VocabName } from '@/lib/dataModelText'

type Lists = { labels: Record<string, string>; descriptions: Record<string, string> }

export const VOCABS: Record<VocabName, Lists> = {
  original_function: { labels: V.ORIGINAL_FUNCTION_LABELS, descriptions: V.ORIGINAL_FUNCTION_DESCRIPTIONS },
  shape_class: { labels: V.SHAPE_CLASS_LABELS, descriptions: V.SHAPE_CLASS_DESCRIPTIONS },
  origin_kind: { labels: V.ORIGIN_KIND_LABELS, descriptions: V.ORIGIN_KIND_DESCRIPTIONS },
  exit_kind: { labels: V.EXIT_KIND_LABELS, descriptions: V.EXIT_KIND_DESCRIPTIONS },
  status: { labels: V.STATUS_LABELS, descriptions: V.STATUS_DESCRIPTIONS },
  precision: { labels: V.PRECISION_LABELS, descriptions: V.PRECISION_DESCRIPTIONS },
  dgnb_class: { labels: V.DGNB_CLASS_LABELS, descriptions: V.DGNB_CLASS_DESCRIPTIONS },
  connection_type: { labels: V.CONNECTION_TYPE_LABELS, descriptions: V.CONNECTION_TYPE_DESCRIPTIONS },
  construction_method: { labels: V.CONSTRUCTION_METHOD_LABELS, descriptions: V.CONSTRUCTION_METHOD_DESCRIPTIONS },
  material_group: { labels: V.MATERIAL_GROUP_LABELS, descriptions: V.MATERIAL_GROUP_DESCRIPTIONS },
  evidence_method: { labels: V.EVIDENCE_METHOD_LABELS, descriptions: V.EVIDENCE_METHOD_DESCRIPTIONS },
  source_tier: { labels: V.SOURCE_TIER_LABELS, descriptions: V.SOURCE_TIER_DESCRIPTIONS },
  verification_state: { labels: V.VERIFICATION_STATE_LABELS, descriptions: V.VERIFICATION_STATE_DESCRIPTIONS },
  quantity: { labels: V.QUANTITY_LABELS, descriptions: V.QUANTITY_DESCRIPTIONS },
}

export type VocabEntry = { value: string; label: string; description: string }

/** The values of a vocabulary in the backend's order, with label and meaning. */
export function vocabEntries(name: VocabName): VocabEntry[] {
  const { labels, descriptions } = VOCABS[name]
  return Object.keys(descriptions).map((value) => ({
    value,
    label: valueLabel(labels, value),
    description: descriptions[value],
  }))
}
