/**
 * CI Dependency Graph — visualizes relationships between configuration items
 * using React Flow.
 * 
 * Backend: GET /cmdb/items/{id}/graph?depth=N
 */
import React, { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactFlow, {
  Node,
  Edge,
  Controls,
  Background,
  MiniMap,
  MarkerType,
} from 'reactflow'
import { cmdbApi } from '../services/api'

interface GraphNode {
  id: string
  name: string
  type_id: number
  type_key?: string
  icon?: string
}

interface GraphEdge {
  source: string
  target: string
  relationship_type: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

const CIDependencyGraph: React.FC<{ itemId: number; depth?: number }> = ({ 
  itemId, 
  depth = 2 
}) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['ci-graph', itemId, depth],
    queryFn: async () => {
      const res = await cmdbApi.getItemGraph(itemId, depth)
      return res.data as GraphData
    },
    enabled: !!itemId,
  })

  const reactFlowNodes: Node[] = useMemo(() => {
    if (!data?.nodes) return []
    return data.nodes.map((node, index) => ({
      id: node.id,
      data: { label: `${node.name}\n(${node.type_key || `type:${node.type_id}`})` },
      position: { x: index * 250, y: 0 },
      type: 'default',
    }))
  }, [data?.nodes])

  const reactFlowEdges: Edge[] = useMemo(() => {
    if (!data?.edges) return []
    return data.edges.map((edge, index) => ({
      id: `e-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.relationship_type,
      markerEnd: MarkerType.ArrowClosed,
      style: { stroke: '#555' },
    }))
  }, [data?.edges])

  if (isLoading) return <div className="loading">Loading dependency graph...</div>
  if (error) return <div className="error">Failed to load graph: {(error as Error).message}</div>
  if (!data?.nodes || data.nodes.length === 0) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>No dependencies found for this CI item.</div>
  }

  return (
    <div style={{ height: '600px', border: '1px solid #ddd', borderRadius: '8px' }}>
      <ReactFlow
        nodes={reactFlowNodes}
        edges={reactFlowEdges}
        fitView
      >
        <Controls />
        <Background />
        <MiniMap />
      </ReactFlow>
    </div>
  )
}

export default CIDependencyGraph
