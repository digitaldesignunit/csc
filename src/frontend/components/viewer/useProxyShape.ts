'use client'

import { useEffect, useMemo } from 'react'

import type { ProxyDoc } from '@/lib/proxyOverlay'
import { buildProxyShape, disposeProxyShape, type ProxyShape } from '@/lib/proxyShape'

/**
 * The faces of a proxy, built once for the solid and the overlay together
 * (decision 8.85). Null while the proxy has no parameters to draw.
 */
export function useProxyShape(proxy: ProxyDoc | null | undefined): ProxyShape | null {
  const shape = useMemo(() => buildProxyShape(proxy), [proxy])
  useEffect(() => () => {
    if (shape) disposeProxyShape(shape)
  }, [shape])
  return shape
}
