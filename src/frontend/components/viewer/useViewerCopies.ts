'use client'

import { useEffect, useLayoutEffect, useMemo } from 'react'
import type * as THREE from 'three'

import { applyOpacityToObject, copyForViewer, disposeViewerCopy } from '@/lib/viewerOpacity'

/**
 * The loaders cache meshes and point clouds across viewers (the module cache
 * keyed by identity), so a viewer draws its own copies of them: the geometry
 * is shared, the materials are its own. The opacity slider fades the copies
 * and never a cached material; a second viewer on the page keeps its own
 * opacity. New layers (another version, a new detail level) arrive as new
 * copies and get the current opacity before they are drawn.
 */
export function useViewerCopies(sources: THREE.Group[], percent: number): THREE.Group[] {
  const copies = useMemo(() => sources.map((source) => copyForViewer(source)), [sources])
  useEffect(() => () => { copies.forEach(disposeViewerCopy) }, [copies])
  useLayoutEffect(() => {
    copies.forEach((copy) => applyOpacityToObject(copy, percent))
  }, [copies, percent])
  return copies
}
