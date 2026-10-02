'use client'

import React, { useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { decodePng16 } from '@/lib/png16'
import {
  channelRange,
  faceTexture,
  placementMatrix,
  proxyFaceGeometries,
  type FaceMap,
  type MapChannel,
  type ProxyDoc,
} from '@/lib/proxyOverlay'

const SCALE = 0.001

export type ProxyDisplay = 'off' | 'outline' | MapChannel

type DeviationFace = { distance: { scale_mm: number; offset_mm: number } }

const MAX_PARALLEL_MAPS = 6

/** Runs ``task`` over ``items``, at most ``limit`` at a time. */
async function inBatches<T, R>(
  items: T[],
  limit: number,
  task: (item: T) => Promise<R>,
): Promise<R[]> {
  const results: R[] = new Array(items.length)
  let next = 0
  const worker = async () => {
    while (next < items.length) {
      const index = next
      next += 1
      results[index] = await task(items[index])
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
  return results
}

/**
 * Fetches and decodes the deviation maps of one proxy --- only while a map
 * overlay is switched on (``enabled``), a few at a time: a prism with a long
 * outline has a map per edge.
 */
export function useDeviationMaps(
  snapshotId: string | undefined,
  proxyIndex: number,
  faces: Record<string, DeviationFace> | undefined,
  enabled: boolean,
): { maps: Record<string, FaceMap> | null; error: string | null } {
  const [state, setState] = useState<{
    key: string
    maps: Record<string, FaceMap> | null
    error: string | null
  }>({ key: '', maps: null, error: null })
  const key = `${snapshotId}:${proxyIndex}:${Object.keys(faces ?? {}).join(',')}`

  useEffect(() => {
    if (!enabled || !snapshotId || !faces || state.key === key) return
    let cancelled = false
    const load = async () => {
      try {
        const entries = await inBatches(
          Object.entries(faces),
          MAX_PARALLEL_MAPS,
          async ([face, doc]) => {
            const url = `/api/backend/snapshots/${encodeURIComponent(snapshotId)}`
              + `/proxies/${proxyIndex}/faces/${encodeURIComponent(face)}`
            const response = await fetch(url, { credentials: 'include' })
            if (!response.ok) throw new Error(`${face}: ${response.status}`)
            const image = await decodePng16(await response.arrayBuffer())
            return [face, {
              image, scaleMm: doc.distance.scale_mm, offsetMm: doc.distance.offset_mm,
            }] as const
          },
        )
        if (!cancelled) setState({ key, maps: Object.fromEntries(entries), error: null })
      } catch (err) {
        if (!cancelled) setState({ key, maps: null, error: String(err) })
      }
    }
    void load()
    return () => { cancelled = true }
  }, [enabled, snapshotId, proxyIndex, faces, key, state.key])

  return state.key === key
    ? { maps: state.maps, error: state.error }
    : { maps: null, error: null }
}

type Props = {
  proxy: ProxyDoc
  display: ProxyDisplay
  maps: Record<string, FaceMap> | null
  /** Called with the colour range (mm, degrees or points) in use. */
  onRange?: (range: number | null) => void
}

/**
 * The proxy drawn in the snapshot's stored coordinates: a wireframe outline,
 * or its faces coloured by one channel of the deviation maps. Meant to sit
 * inside the viewer's component group.
 */
export default function ProxyOverlay({ proxy, display, maps, onRange }: Props) {
  const faces = useMemo(() => proxyFaceGeometries(proxy), [proxy])
  const matrix = useMemo(() => placementMatrix(proxy.placement), [proxy])
  const channel: MapChannel | null =
    display === 'off' || display === 'outline' ? null : display
  const range = useMemo(
    () => (maps && channel ? channelRange(maps, channel) : 1),
    [maps, channel],
  )
  useEffect(() => {
    onRange?.(channel && maps ? range : null)
  }, [onRange, channel, maps, range])
  const edges = useMemo(
    () => Object.fromEntries(
      Object.entries(faces).map(([face, geometry]) => [face, new THREE.EdgesGeometry(geometry, 30)]),
    ),
    [faces],
  )
  const textures = useMemo(() => {
    if (!maps || !channel) return {}
    return Object.fromEntries(
      Object.entries(maps).map(([face, map]) => [face, faceTexture(map, channel, range)]),
    )
  }, [maps, channel, range])

  useEffect(() => () => {
    Object.values(faces).forEach((geometry) => geometry.dispose())
    Object.values(edges).forEach((geometry) => geometry.dispose())
  }, [faces, edges])
  useEffect(() => () => {
    Object.values(textures).forEach((texture) => (texture as THREE.Texture).dispose())
  }, [textures])

  if (display === 'off') return null
  return (
    <group scale={[SCALE, SCALE, SCALE]} rotation={[-Math.PI / 2, 0, 0]}>
      <group matrixAutoUpdate={false} matrix={matrix}>
        {Object.entries(faces).map(([face, geometry]) => {
          const texture = (textures as Record<string, THREE.Texture>)[face]
          return (
            <group key={face}>
              {texture && (
                <mesh geometry={geometry}>
                  <meshBasicMaterial
                    map={texture}
                    transparent
                    side={THREE.DoubleSide}
                    polygonOffset
                    polygonOffsetFactor={-1}
                  />
                </mesh>
              )}
              <lineSegments geometry={edges[face]}>
                <lineBasicMaterial color={0x2563eb} />
              </lineSegments>
            </group>
          )
        })}
      </group>
    </group>
  )
}
