'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import ELK from 'elkjs/lib/elk.bundled.js'
import '@xyflow/react/dist/style.css'

import type {
  ProvenanceGraph,
  ProvenanceIdentityNode,
  ProvenanceSnapshotNode,
} from '@/generated/catalogExtras'
import { isConsumedShallowRow } from './componentDetailShared'
import { cn } from '@/lib/utils'

type IdentityData = {
  identityId: string
  name: string | null
  consumed: boolean
  isRoot: boolean
}

type SnapshotData = {
  snapshotId: string
  identityId: string
  version: number
  virtual: boolean
  isCurrent: boolean
  name: string | null
}

type IdentityFlowNode = Node<IdentityData, 'identity'>
type SnapshotFlowNode = Node<SnapshotData, 'snapshot'>
type FlowNode = IdentityFlowNode | SnapshotFlowNode

const IDENTITY_WIDTH = 248
const IDENTITY_HEIGHT = 64
const SNAPSHOT_WIDTH = 220
const SNAPSHOT_HEIGHT = 52

const elk = new ELK()

function IdentityProvenanceNode({ data }: NodeProps<IdentityFlowNode>) {
  return (
    <div
      className={cn(
        'h-full w-full rounded-md border px-2 py-1.5 shadow-sm',
        data.consumed
          ? 'border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100'
          : 'border-green-300 bg-green-100 text-green-900 dark:border-green-700 dark:bg-green-950/50 dark:text-green-100',
        data.isRoot && 'ring-2 ring-primary ring-offset-1 ring-offset-background',
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2" />
      <div className="flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] bg-black/10 font-sans text-[9px] font-bold leading-none dark:bg-white/15"
        >
          {data.consumed ? 'C' : 'A'}
        </span>
        <span className="truncate text-[10px] font-semibold">
          {data.isRoot ? 'This identity' : data.name || 'Identity'}
        </span>
      </div>
      <p className="mt-1 font-mono text-[9px] leading-tight break-all">{data.identityId}</p>
    </div>
  )
}

function SnapshotProvenanceNode({ data }: NodeProps<SnapshotFlowNode>) {
  return (
    <div className="h-full w-full rounded-md border border-border bg-card px-2 py-1.5 text-foreground shadow-sm">
      <Handle type="target" position={Position.Left} className="!h-2 !w-2" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2" />
      <p className="text-[10px] font-semibold">
        Snapshot v{data.version}
        {data.isCurrent ? ' · live' : ''}
        {data.virtual ? ' · virtual' : ''}
      </p>
      <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
        {data.name || data.snapshotId}
      </p>
    </div>
  )
}

const nodeTypes = {
  identity: IdentityProvenanceNode,
  snapshot: SnapshotProvenanceNode,
}

function edgeStroke(kind: ProvenanceGraph['edges'][number]['kind']): string {
  if (kind === 'parent') return 'var(--primary)'
  if (kind === 'version') return 'var(--muted-foreground)'
  return 'var(--border)'
}

async function layoutGraph(graph: ProvenanceGraph): Promise<{
  nodes: FlowNode[]
  edges: Edge[]
}> {
  const children = graph.nodes.map((node) => ({
    id: node.id,
    width: node.kind === 'identity' ? IDENTITY_WIDTH : SNAPSHOT_WIDTH,
    height: node.kind === 'identity' ? IDENTITY_HEIGHT : SNAPSHOT_HEIGHT,
  }))
  const elkGraph = await elk.layout({
    id: 'provenance',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.layered.spacing.nodeNodeBetweenLayers': '72',
      'elk.spacing.nodeNode': '28',
      'elk.edgeRouting': 'ORTHOGONAL',
    },
    children,
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  })

  const positions = new Map(
    (elkGraph.children ?? []).map((child) => [child.id, child] as const),
  )

  const nodes: FlowNode[] = graph.nodes.map((node) => {
    const laidOut = positions.get(node.id)
    const position = { x: laidOut?.x ?? 0, y: laidOut?.y ?? 0 }
    if (node.kind === 'identity') {
      const identity = node as ProvenanceIdentityNode
      return {
        id: node.id,
        type: 'identity',
        position,
        data: {
          identityId: identity.identity_id,
          name: identity.name ?? null,
          consumed: isConsumedShallowRow({ consumed_at: identity.consumed_at }),
          isRoot: identity.is_root,
        },
        style: { width: IDENTITY_WIDTH, height: IDENTITY_HEIGHT },
      } satisfies IdentityFlowNode
    }
    const snapshot = node as ProvenanceSnapshotNode
    return {
      id: node.id,
      type: 'snapshot',
      position,
      data: {
        snapshotId: snapshot.snapshot_id,
        identityId: snapshot.identity_id,
        version: snapshot.version,
        virtual: Boolean(snapshot.virtual),
        isCurrent: snapshot.is_current,
        name: typeof snapshot.name === 'string' ? snapshot.name : null,
      },
      style: { width: SNAPSHOT_WIDTH, height: SNAPSHOT_HEIGHT },
    } satisfies SnapshotFlowNode
  })

  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    style: { stroke: edgeStroke(edge.kind), strokeWidth: edge.kind === 'parent' ? 2 : 1.5 },
  }))

  return { nodes, edges }
}

type ComponentProvenanceGraphProps = {
  graph: ProvenanceGraph
  onNavigate: () => void
}

export default function ComponentProvenanceGraph({
  graph,
  onNavigate,
}: ComponentProvenanceGraphProps) {
  const router = useRouter()
  const [nodes, setNodes] = useState<FlowNode[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [layoutError, setLayoutError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLayoutError(null)
    layoutGraph(graph)
      .then((laidOut) => {
        if (!cancelled) {
          setNodes(laidOut.nodes)
          setEdges(laidOut.edges)
        }
      })
      .catch((error: unknown) => {
        console.error('Failed to layout provenance graph:', error)
        if (!cancelled) {
          setLayoutError('Could not lay out the lineage graph.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [graph])

  const nodeTypesMemo = useMemo(() => nodeTypes, [])

  if (layoutError) {
    return <p className="p-4 text-sm text-destructive">{layoutError}</p>
  }

  if (nodes.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">Preparing graph…</p>
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypesMemo}
        onNodeClick={(_event, node) => {
          if (node.type === 'identity') {
            const data = node.data as IdentityData
            onNavigate()
            router.push(`/components/${encodeURIComponent(data.identityId)}`)
            return
          }
          const data = node.data as SnapshotData
          onNavigate()
          const params = new URLSearchParams({ snapshots: data.snapshotId })
          router.push(
            `/components/${encodeURIComponent(data.identityId)}?${params.toString()}`,
          )
        }}
        fitView
        minZoom={0.15}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        className="bg-muted/20"
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  )
}
