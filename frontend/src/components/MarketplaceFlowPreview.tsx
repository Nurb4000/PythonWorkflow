import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
} from '@xyflow/react'
import { marketplaceApi } from '../services/api'
import '@xyflow/react/dist/style.css'

const END_TARGET = -1

const nodeTypeInfo: Record<string, { icon: string; bg: string; border: string }> = {
  api_call:      { icon: '\ud83c\udf10', bg: '#e3f2fd', border: '#1565c0' },
  database_query:{ icon: '\ud83d\uddc4\ufe0f', bg: '#e8f5e9', border: '#2e7d32' },
  email:         { icon: '\u2709\ufe0f', bg: '#fff3e0', border: '#ef6c00' },
  condition:     { icon: '\u2753', bg: '#fce4ec', border: '#c2185b' },
  form:          { icon: '\ud83d\udcdd', bg: '#f3e5f5', border: '#7b1fa2' },
  delay:         { icon: '\u23f1\ufe0f', bg: '#e0f7fa', border: '#00838f' },
  human_task:    { icon: '\ud83d\udc64', bg: '#fff8e1', border: '#ff8f00' },
  approval:      { icon: '\u2705', bg: '#e8f5e9', border: '#388e3c' },
  webhook:       { icon: '\ud83d\udd17', bg: '#e1f5fe', border: '#0288d1' },
  custom_code:   { icon: '\ud83d\udcbb', bg: '#f3e5f5', border: '#7b1fa2' },
  calculation:   { icon: '\ud83d\udd22', bg: '#fff3e0', border: '#ef6c00' },
  report:        { icon: '\ud83d\udcca', bg: '#e8eaf6', border: '#3f51b5' },
  cmdb_lookup:   { icon: '\ud83d\udd0d', bg: '#e0f2f1', border: '#00695c' },
  cmdb_update:   { icon: '\u270f\ufe0f', bg: '#e8f5e9', border: '#2e7d32' },
}

const StartNode: React.FC = () => (
  <div>
    <Handle type="target" position={Position.Top} style={{ background: '#27ae60', width: 8, height: 8 }} />
    <div style={{
      width: 44, height: 44, borderRadius: '50%', background: '#27ae60',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontSize: '1.1rem', border: '3px solid #fff',
      boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
    }}>▶</div>
    <Handle type="source" position={Position.Bottom} style={{ background: '#27ae60', width: 8, height: 8 }} />
  </div>
)

const EndNode: React.FC = () => (
  <div>
    <Handle type="target" position={Position.Top} style={{ background: '#e74c3c', width: 8, height: 8 }} />
    <div style={{
      width: 44, height: 44, borderRadius: '50%', background: '#e74c3c',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontSize: '1rem', border: '3px solid #fff',
      boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
    }}>⏹</div>
  </div>
)

const StepNode: React.FC<any> = ({ data }) => (
  <div>
    <Handle type="target" position={Position.Top} style={{ background: data.border || '#999', width: 8, height: 8 }} />
    <div style={{
      padding: '10px 16px', borderRadius: '8px', background: data.bg || '#f5f5f5',
      border: `2px solid ${data.border || '#999'}`, minWidth: '170px', textAlign: 'center',
      fontSize: '0.85rem', fontWeight: 500, color: '#333', cursor: 'pointer',
    }}>
      <div style={{ fontSize: '1.3rem' }}>{data.icon || '\ud83d\udce6'}</div>
      <div style={{ fontWeight: 600 }}>{data.title}</div>
      {data.description && (
        <div style={{ fontSize: '0.7rem', color: '#777', marginTop: '4px', lineHeight: 1.3 }}>
          {data.description.length > 80 ? data.description.substring(0, 80) + '...' : data.description}
        </div>
      )}
    </div>
    <Handle type="source" position={Position.Bottom} style={{ background: data.border || '#999', width: 8, height: 8 }} />
  </div>
)

const nodeTypes = { startNode: StartNode, endNode: EndNode, stepNode: StepNode }

const FlowGraph: React.FC<{ graphData: any }> = ({ graphData }) => {
  const toNum = (v: any) => (typeof v === 'string' ? Number(v) : v)
  const steps = graphData.steps
  const stepMap = useMemo(() => new Map(steps.map((s: any) => [s.id, s])), [steps])
  const [selectedStep, setSelectedStep] = useState<any>(null)

  const [nodes] = useNodesState(
    [
      { id: 'start', type: 'startNode', position: { x: 250, y: 0 }, data: { label: 'Start' } },
      ...steps.map((step: any, index: number) => {
        const info = nodeTypeInfo[step.step_type] || { icon: '\ud83d\udce6', bg: '#f5f5f5', border: '#999' }
        return {
          id: `step-${step.id}`,
          type: 'stepNode',
          position: { x: 250, y: 100 + (index * 130) },
          data: {
            icon: info.icon,
            title: step.title || step.step_type,
            description: step.description || '',
            bg: info.bg,
            border: info.border,
            stepData: step,
          },
        }
      }),
      { id: 'end', type: 'endNode', position: { x: 250, y: 100 + (steps.length * 130) }, data: { label: 'End' } },
    ]
  )

  const [edges] = useEdgesState(useMemo(() => {
    const result: any[] = []

    let startIds = (graphData.start_step_ids || [])
      .map(toNum)
      .filter((sid: number) => stepMap.has(sid))

    // Fallback: if no start_step_ids, connect to steps at position 0
    if (startIds.length === 0 && steps.length > 0) {
      const firstSteps = steps.filter((s: any) => s.position === 0)
      startIds = firstSteps.map((s: any) => s.id)
    }

    startIds.forEach((sid: number) => {
      result.push({
        id: `e-start-${sid}`,
        source: 'start', target: `step-${sid}`,
        animated: true,
        style: { strokeWidth: 2, stroke: '#27ae60' },
      })
    })

    // Track which steps have outgoing edges
    const hasOutgoing = new Set<number>()

    steps.forEach((step: any) => {
      const def = step.definition || {}
      if (step.step_type === 'condition') {
        const routes = def.routes || []
        let hasRoute = false
        routes.forEach((route: any, i: number) => {
          const numTarget = toNum(route.target_step_id)
          if (numTarget && (numTarget === END_TARGET || stepMap.has(numTarget))) {
            hasRoute = true
            result.push({
              id: `e-${step.id}-r${i}`,
              source: `step-${step.id}`,
              target: numTarget === END_TARGET ? 'end' : `step-${numTarget}`,
              animated: true,
              label: route.expression || `Route ${i + 1}`,
              style: { strokeWidth: 2, stroke: '#c2185b', fontSize: 10 },
            })
          }
        })
        const numDefault = toNum(def.default_target_step_id)
        if (numDefault && (numDefault === END_TARGET || stepMap.has(numDefault))) {
          hasRoute = true
          result.push({
            id: `e-${step.id}-def`,
            source: `step-${step.id}`,
            target: numDefault === END_TARGET ? 'end' : `step-${numDefault}`,
            animated: true, label: 'Else',
            style: { strokeWidth: 2, stroke: '#95a5a6', fontSize: 10 },
          })
        }
        if (hasRoute) hasOutgoing.add(step.id)
      } else {
        const targets = def.next_step_ids || (def.next_step_id ? [def.next_step_id] : [])
        let hasTarget = false
        targets.forEach((targetId: number, i: number) => {
          const numTarget = toNum(targetId)
          if (numTarget && (numTarget === END_TARGET || stepMap.has(numTarget))) {
            hasTarget = true
            result.push({
              id: `e-${step.id}-o${i}`,
              source: `step-${step.id}`,
              target: numTarget === END_TARGET ? 'end' : `step-${numTarget}`,
              animated: true,
              style: { strokeWidth: 2, stroke: '#95a5a6' },
            })
          }
        })
        if (hasTarget) hasOutgoing.add(step.id)
      }
    })

    // Auto-connect terminal steps (no outgoing edges) to the End node
    steps.forEach((step: any) => {
      if (!hasOutgoing.has(step.id)) {
        result.push({
          id: `e-terminal-${step.id}`,
          source: `step-${step.id}`,
          target: 'end',
          animated: true,
          style: { strokeWidth: 2, stroke: '#95a5a6' },
        })
      }
    })

    return result
  }, [steps, graphData.start_step_ids, stepMap]))

  const handleNodeClick = (_: any, node: any) => {
    if (!node.id.startsWith('step-')) {
      setSelectedStep(null)
      return
    }
    const stepId = parseInt(node.id.replace('step-', ''))
    const step = stepMap.get(stepId)
    if (step) {
      setSelectedStep(step)
    }
  }

  return (
    <div>
      <div style={{ height: '480px', borderRadius: '6px', overflow: 'hidden', border: '1px solid #eee' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          zoomOnScroll
          panOnScroll
          onNodeClick={handleNodeClick}
        >
          <Background color="#eee" gap={16} />
          <Controls />
        </ReactFlow>
      </div>

      {selectedStep && (
        <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h4 style={{ margin: 0 }}>
              {nodeTypeInfo[selectedStep.step_type]?.icon || '\ud83d\udce6'} Step Details: {selectedStep.title || selectedStep.step_type}
            </h4>
            <button className="btn btn-sm btn-secondary" onClick={() => setSelectedStep(null)}>✕ Close</button>
          </div>

          {selectedStep.description && (
            <p style={{ color: '#666', fontSize: '0.9rem', margin: '0 0 0.75rem' }}>{selectedStep.description}</p>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <div><strong>Step Type:</strong> {selectedStep.step_type}</div>
            <div><strong>Position:</strong> {selectedStep.position}</div>
          </div>

          {selectedStep.step_type === 'condition' && (selectedStep.definition?.routes || []).length > 0 && (
            <div style={{ marginBottom: '0.75rem' }}>
              <strong>Routes:</strong>
              <ul style={{ margin: '0.25rem 0 0 1.25rem', fontSize: '0.85rem' }}>
                {(selectedStep.definition.routes || []).map((route: any, i: number) => (
                  <li key={i}>
                    <code>{route.expression || `Route ${i + 1}`}</code> →{' '}
                    {route.target_step_id === END_TARGET ? 'End' : route.target_step_id ? `Step #${route.target_step_id}` : 'Unconnected'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(selectedStep.definition?.next_step_ids || []).length > 0 && (
            <div style={{ marginBottom: '0.75rem' }}>
              <strong>Outputs:</strong>{' '}
              {(selectedStep.definition.next_step_ids || []).map((tid: number, i: number) => (
                <span key={i}>
                  {tid === END_TARGET ? 'End' : `Step #${tid}`}
                  {i < (selectedStep.definition.next_step_ids || []).length - 1 ? ', ' : ''}
                </span>
              ))}
            </div>
          )}

          <details>
            <summary style={{ cursor: 'pointer', fontWeight: 'bold', fontSize: '0.85rem' }}>Step Definition (JSON)</summary>
            <pre style={{ background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem', overflow: 'auto', maxHeight: '200px', marginTop: '0.5rem' }}>
              {JSON.stringify(selectedStep.definition, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  )
}

export const MarketplaceFlowPreview: React.FC<{ itemId: number }> = ({ itemId }) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['marketplace-graph', itemId],
    queryFn: async () => {
      const res = await marketplaceApi.getItemGraph(itemId)
      return res.data
    },
    enabled: !!itemId,
  })

  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: '3rem', color: '#7f8c8d' }}>Loading workflow graph...</div>
  }
  if (error || !data) {
    return <div style={{ textAlign: 'center', padding: '2rem', color: '#e74c3c' }}>Failed to load workflow graph</div>
  }
  if (data.error) {
    return <div style={{ textAlign: 'center', padding: '2rem', color: '#e67e22' }}>{data.error}</div>
  }
  if (!data.steps || data.steps.length === 0) {
    return <div style={{ textAlign: 'center', padding: '2rem', color: '#7f8c8d' }}>No steps in this workflow</div>
  }

  return (
    <ReactFlowProvider>
      <FlowGraph graphData={data} />
    </ReactFlowProvider>
  )
}
