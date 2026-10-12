/**
 * The descriptor bases the component map offers. The API also accepts `hks`
 * (the cache job still computes it), but the pooled heat kernel signature is
 * not offered while `HKS_VISIBLE` is off (`lib/hks.ts`): its mass-weighted mean
 * half is nearly shape-independent after area normalisation.
 */
import { HKS_VISIBLE } from '@/lib/hks'

export type MapBasisOption = { value: 'radial_signature' | 'scalars' | 'hks'; label: string }

const ALL: MapBasisOption[] = [
  { value: 'radial_signature', label: 'Radial signature' },
  { value: 'scalars', label: 'Scalar descriptors' },
  { value: 'hks', label: 'Heat kernel signature' },
]

export function mapBasisOptions(showHks: boolean = HKS_VISIBLE): MapBasisOption[] {
  return ALL.filter((option) => option.value !== 'hks' || showHks)
}
