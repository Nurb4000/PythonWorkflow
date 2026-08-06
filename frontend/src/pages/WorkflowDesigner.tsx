import React, { useState, useCallback, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { produce } from 'immer'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  Node,
  Edge,
  MarkerType,
  ReactFlowProvider,
  useUpdateNodeInternals
} from 'react-flow-renderer'
import { workflowApi, authApi, aiApi, dataQueryApi, marketplaceApi } from '../services/api'
import { QueryBuilder, VisualQuery, TableInfo } from '../components/QueryBuilder'
import axios from 'axios'
import 'react-flow-renderer/dist/style.css'

const API_URL = '/api'

interface WorkflowStep {
  id: number
  workflow_id?: number
  step_type: string
  definition: any
  position: number
  condition_expr: string
  is_enabled: boolean
  title?: string
  description?: string
  max_retries?: number
  retry_delay_seconds?: number
  failure_hook_url?: string
}

interface Workflow {
  id: number
  name: string
  steps: WorkflowStep[]
}

interface Form {
  id: number
  name: string
  is_published: boolean
}

interface UserOption {
  id: number
  username: string
  full_name: string
  email: string
}

interface GroupOption {
  id: number
  name: string
}

const stepTypeToNodeType = (stepType: string): string => {
  const map: Record<string, string> = {
    api_call: 'apiCall',
    database_query: 'databaseQuery',
    delay: 'delay',
    human_task: 'humanTask',
    approval: 'approval',
    webhook: 'webhook',
    custom_code: 'customCode',
    calculation: 'calculation',
    report: 'report'
  }
  return map[stepType] || stepType
}

const NODE_WIDTH = 170
const NODE_HEIGHT = 70

function getNodeStyle(stepType: string) {
  const base: any = { position: 'relative' }
  switch (stepType) {
    case 'apiCall':
      return { ...base, background: '#e3f2fd', border: '2px solid #1565c0' }
    case 'databaseQuery':
      return { ...base, background: '#e8f5e9', border: '2px solid #2e7d32' }
    case 'email':
      return { ...base, background: '#fff3e0', border: '2px solid #ef6c00' }
    case 'condition':
      return { ...base, background: '#fce4ec', border: '2px solid #c2185b' }
    case 'form':
      return { ...base, background: '#f3e5f5', border: '2px solid #7b1fa2' }
    case 'delay':
      return { ...base, background: '#e0f7fa', border: '2px solid #00838f' }
    case 'human_task':
      return { ...base, background: '#fff8e1', border: '2px solid #ff8f00' }
    case 'approval':
      return { ...base, background: '#e8f5e9', border: '2px solid #388e3c' }
    case 'webhook':
      return { ...base, background: '#e1f5fe', border: '2px solid #0288d1' }
    case 'custom_code':
      return { ...base, background: '#f3e5f5', border: '2px solid #7b1fa2' }
    case 'calculation':
      return { ...base, background: '#fff3e0', border: '2px solid #ef6c00' }
    case 'report':
      return { ...base, background: '#e8eaf6', border: '2px solid #3f51b5' }
    case 'start':
      return { ...base, background: '#27ae60', border: 'none', color: 'white', borderRadius: '20px' }
    case 'end':
      return { ...base, background: '#e74c3c', border: 'none', color: 'white', borderRadius: '20px' }
    default:
      return { ...base, background: '#eee', border: '2px solid #666' }
  }
}

function nodeLabel(stepType: string, data: any) {
  switch (stepType) {
    case 'apiCall': return `🌐 ${data.method || 'GET'} ${data.url || 'API Call'}`
    case 'databaseQuery': {
      const hasVisual = !!data.visual_query
      return `🗄️ ${data.query_type || 'SELECT'} ${data.table || ''}${hasVisual ? ' (visual)' : ''}`
    }
    case 'email': return `📧 To: ${data.to || 'N/A'}`
    case 'condition': {
      // P4.1: Show first route expression instead of legacy condition_expr
      const firstRoute = data.routes?.[0]
      const expr = firstRoute?.expression || data.condition_expr || 'Condition'
      return `❓ ${expr}`
    }
    case 'form': return `📝 ${data.form_name || `Form #${data.form_id || ''}`}`
    case 'human_task': return `👤 ${data.title || 'Human Task'}`
    case 'approval': return `✅ ${data.title || 'Approval'}`
    case 'webhook': return `🔗 Webhook: ${data.url || '...'}`
    case 'custom_code': return `💻 Custom Code`
    case 'calculation': return `🧮 ${data.title || 'Calculation'}`
    case 'report': {
      const hasVisual = !!data.visual_query
      return `📊 ${data.title || (data.report_type === 'sql_query' ? 'SQL Query' : 'Report')}${hasVisual ? ' (visual)' : ''}`
    }
    default: return stepType
  }
}

const renderStepNode = (data: any, cfg: { icon: string; title: string; subtitle?: string; style: any }) => {
  const count = Math.max(1, data.next_step_ids?.length || 1)
  const displayTitle = data.title || cfg.title
  const displaySubtitle = data.description || cfg.subtitle
  
  return (
    <div style={{ padding: '10px 16px', borderRadius: '8px', minWidth: '150px', cursor: 'pointer', ...cfg.style }}>
      <Handle type="target" position={Position.Top} />
      <strong>{cfg.icon} {displayTitle}</strong>
      {displaySubtitle && <div style={{ fontSize: '0.7rem', marginTop: '3px', wordBreak: 'break-word', opacity: 0.8 }}>{displaySubtitle}</div>}
      {Array.from({ length: count }).map((_, i) => (
        <Handle key={i} type="source" position={Position.Bottom} id={`out-${i}`}
          style={{ left: `${((i + 1) * 100) / (count + 1)}%`, background: '#1565c0' }} />
      ))}
    </div>
  )
}

const nodeTypes = {
  apiCall: ({ data }: any) => renderStepNode(data, {
    icon: '🌐', title: 'API Call',
    subtitle: `${data.method || 'GET'} ${data.url || ''}`,
    style: getNodeStyle('apiCall')
  }),
  databaseQuery: ({ data }: any) => renderStepNode(data, {
    icon: '🗄️', title: 'Database',
    subtitle: `${data.query_type || 'SELECT'} ${data.table || ''}`,
    style: getNodeStyle('databaseQuery')
  }),
  email: ({ data }: any) => renderStepNode(data, {
    icon: '📧', title: 'Email',
    subtitle: `To: ${data.to || 'N/A'}`,
    style: getNodeStyle('email')
  }),
  form: ({ data }: any) => renderStepNode(data, {
    icon: '📝', title: 'Form',
    subtitle: `${data.form_name || `Form #${data.form_id || ''}`}`,
    style: getNodeStyle('form')
  }),
  delay: ({ data }: any) => renderStepNode(data, {
    icon: '⏱', title: 'Delay',
    subtitle: `${data.seconds || 0}s`,
    style: getNodeStyle('delay')
  }),
  condition: ({ data }: any) => {
    const displayTitle = data.title || 'Condition'
    // P4.1: Show first route expression on the node
    const firstRoute = data.routes?.[0]
    const displayExpr = firstRoute?.expression || data.condition_expr || ''
    return (
      <div style={{ padding: '10px 16px', borderRadius: '8px', minWidth: '180px', cursor: 'pointer', ...getNodeStyle('condition') }}>
        <Handle type="target" position={Position.Top} />
        <strong>❓ {displayTitle}</strong>
        {data.description && <div style={{ fontSize: '0.7rem', marginTop: '3px', opacity: 0.8 }}>{data.description}</div>}
        {displayExpr && <div style={{ fontSize: '0.65rem', marginTop: '2px', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '160px' }}>{displayExpr}</div>}
        {data.routes?.map((_: any, i: number) => (
          <Handle key={i} type="source" position={Position.Bottom} id={`route-${i}`}
            style={{ left: `${(i + 1) * 100 / ((data.routes?.length || 1) + 1)}%`, background: '#27ae60' }} />
        ))}
        <Handle type="source" position={Position.Bottom} id="default"
          style={{ left: '90%', background: '#e74c3c' }} />
      </div>
    )
  },
  start: ({ data }: any) => (
    <div style={{ padding: '10px 24px', borderRadius: '20px', minWidth: '120px', textAlign: 'center', cursor: 'pointer', ...getNodeStyle('start') }}>
      <strong>▶ Start</strong>
      {data.startStepIds?.map((_: any, i: number) => (
        <Handle key={i} type="source" position={Position.Bottom} id={`start-out-${i}`}
          style={{ left: `${((i + 1) * 100) / ((data.startStepIds?.length || 1) + 1)}%`, background: '#27ae60' }} />
      ))}
    </div>
  ),
  end: ({ data }: any) => (
    <div style={{ padding: '10px 24px', borderRadius: '20px', minWidth: '120px', textAlign: 'center', cursor: 'pointer', ...getNodeStyle('end') }}>
      <Handle type="target" position={Position.Top} />
      <strong>■ End</strong>
    </div>
  ),
  humanTask: ({ data }: any) => {
    const assignee = data.assigned_user_name || (data.assigned_group_name ? `Group: ${data.assigned_group_name}` : 'Unassigned')
    return renderStepNode(data, {
      icon: '👤', title: 'Human Task',
      subtitle: data.description || `To: ${assignee}`,
      style: getNodeStyle('human_task')
    })
  },
  approval: ({ data }: any) => {
    const assignee = data.assigned_user_name || (data.assigned_group_name ? `Group: ${data.assigned_group_name}` : 'Unassigned')
    const formLabel = data.form_name ? `Form: ${data.form_name}` : (data.form_id ? `Form #${data.form_id}` : 'No form')
    return renderStepNode(data, {
      icon: '✅', title: 'Approval',
      subtitle: data.description || `${assignee} · ${formLabel}`,
      style: getNodeStyle('approval')
    })
  },
  webhook: ({ data }: any) => renderStepNode(data, {
    icon: '🔗', title: 'Webhook',
    subtitle: data.url || 'No URL',
    style: getNodeStyle('webhook')
  }),
  customCode: ({ data }: any) => renderStepNode(data, {
    icon: '💻', title: 'Custom Code',
    subtitle: data.code ? 'Code step' : 'No code',
    style: getNodeStyle('custom_code')
  }),
  calculation: ({ data }: any) => renderStepNode(data, {
    icon: '🧮', title: 'Calculation',
    subtitle: data.expression || 'No expression',
    style: getNodeStyle('calculation')
  }),
  report: ({ data }: any) => renderStepNode(data, {
    icon: '📊', title: 'Report',
    subtitle: data.report_type === 'sql_query' ? 'SQL Query' : (data.report_type || 'Table Report'),
    style: getNodeStyle('report')
  })
}

const edgeBase = { style: { strokeWidth: 4 }, markerEnd: { type: MarkerType.ArrowClosed } }

// Sentinel value used in a step's connection targets to mean "this path ends here"
const END_TARGET = -1

// My Nodes Library component — fetches and displays saved node templates
const MyNodesList: React.FC<{ onSelect: (node: any) => void }> = ({ onSelect }) => {
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    marketplaceApi.listMyNodes()
      .then(res => setNodes(res.data))
      .catch(() => setError('Failed to load My Nodes'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: '1rem', color: '#95a5a6' }}>Loading...</div>
  if (error) return <div style={{ textAlign: 'center', padding: '1rem', color: '#e74c3c' }}>{error}</div>
  if (nodes.length === 0) return <div style={{ textAlign: 'center', padding: '1rem', color: '#95a5a6' }}>No saved nodes yet. Save a node from the step editor.</div>

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '0.75rem' }}>
      {nodes.map(node => (
        <div
          key={node.id}
          style={{
            padding: '0.75rem', border: '1px solid #ddd', borderRadius: '6px', background: '#fafafa',
            cursor: 'pointer', transition: 'border-color 0.2s, box-shadow 0.2s'
          }}
          onClick={() => onSelect(node)}
          onMouseEnter={(e: React.MouseEvent<HTMLDivElement>) => {
            e.currentTarget.style.borderColor = '#3498db'
            e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'
          }}
          onMouseLeave={(e: React.MouseEvent<HTMLDivElement>) => {
            e.currentTarget.style.borderColor = '#ddd'
            e.currentTarget.style.boxShadow = 'none'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
            <strong style={{ fontSize: '0.9rem' }}>{node.title}</strong>
            <span className="badge badge-info" style={{ fontSize: '0.7rem' }}>{node.step_type}</span>
          </div>
          {node.description && (
            <p style={{ color: '#666', fontSize: '0.8rem', margin: '0.25rem 0', lineHeight: 1.3 }}>
              {node.description.length > 80 ? node.description.substring(0, 80) + '...' : node.description}
            </p>
          )}
          <small style={{ color: '#95a5a6' }}>Click to insert into workflow</small>
        </div>
      ))}
    </div>
  )
}

const edgeColor = (color: string) => ({
  ...edgeBase,
  style: { ...edgeBase.style, stroke: color },
  markerEnd: { ...edgeBase.markerEnd, color }
})

// React Flow only re-measures node handle positions when a node's dimensions change.
// Handles are absolutely positioned, so adding/removing them (start outputs, step connections)
// leaves the stored handle bounds stale and edges connected to them get dropped.
// We force a handle-bounds refresh whenever a node's connection handles change.
const CanvasFlow: React.FC<{
  nodes: Node[]
  edges: Edge[]
  onNodesChange: (changes: any[]) => void
  onNodeDragStop: (event: any, node: Node) => void
  onNodeClick: (event: any, node: Node) => void
  onNodesInitialized?: (instance: any) => void
}> = ({ nodes, edges, onNodesChange, onNodeDragStop, onNodeClick, onNodesInitialized }) => {
  const updateNodeInternals = useUpdateNodeInternals()

  const handleSignature = nodes
    .map((n: any) => {
      const d = n.data || {}
      if (n.id === 'start') return `start:${(d.startStepIds || []).join(',')}`
      const next = (d.next_step_ids || []).join(',') || d.next_step_id || ''
      const routes = (d.routes || []).map((r: any) => r.target_step_id || '').join(',')
      return `${n.id}:${next}|${routes}|${d.default_target_step_id || ''}`
    })
    .sort()
    .join(';')

  useEffect(() => {
    const ids = nodes.map((n) => n.id)
    const timer = window.setTimeout(() => {
      ids.forEach((id) => updateNodeInternals(id))
    }, 60)
    return () => window.clearTimeout(timer)
  }, [handleSignature, nodes, updateNodeInternals])

  return (
    <div className="workflow-designer">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onNodeDragStop={onNodeDragStop}
        onNodeClick={onNodeClick}
        onInit={onNodesInitialized}
        nodeTypes={nodeTypes}
        nodesConnectable={false}
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  )
}

export const WorkflowDesigner: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const workflowId = parseInt(id!)

  const [nodes, setNodes] = useState<Node[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [selectedStep, setSelectedStep] = useState<WorkflowStep | null>(null)
  const [showAddStep, setShowAddStep] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')

  // Per-node AI assist state
  const [nodeAiPanelOpen, setNodeAiPanelOpen] = useState(false)
  const [nodeAiPrompt, setNodeAiPrompt] = useState('')
  const [nodeAiLoading, setNodeAiLoading] = useState(false)
  const [nodeAiResponse, setNodeAiResponse] = useState<any>(null)
  const [nodeAiError, setNodeAiError] = useState('')
  const [editingDef, setEditingDef] = useState<any>({})
  const [editingTitle, setEditingTitle] = useState('')
  const [editingDescription, setEditingDescription] = useState('')
  // Local draft state — nothing is persisted until "Save Workflow" is clicked.
  const [draftSteps, setDraftSteps] = useState<WorkflowStep[]>([])
  const [configDraft, setConfigDraft] = useState<any>({})
  const [deletedStepIds, setDeletedStepIds] = useState<number[]>([])
  const [isDirty, setIsDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [savedMessage, setSavedMessage] = useState('')
  const nodePositions = useRef<Record<string, { x: number; y: number }>>({})
  const reactFlowInstance = useRef<any>(null)

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: async () => {
      const response = await workflowApi.get(workflowId)
      return response.data as any
    },
    enabled: !!id
  })

  const { data: forms } = useQuery({
    queryKey: ['forms'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/forms`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data as Form[]
    }
  })

  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await authApi.listUsers()
      return response.data as UserOption[]
    }
  })

  const { data: groups } = useQuery({
    queryKey: ['groups'],
    queryFn: async () => {
      const response = await authApi.listGroups()
      return response.data as GroupOption[]
    }
  })

  // Tables for QueryBuilder in database_query steps
  const { data: dbTables } = useQuery({
    queryKey: ['data-tables'],
    queryFn: async () => {
      const res = await dataQueryApi.listTables()
      return res.data as TableInfo[]
    },
  })

  // Visual query state for database_query step editor
  const [dbVisualMode, setDbVisualMode] = useState(false)
  const [dbVisualQuery, setDbVisualQuery] = useState<VisualQuery>({
    table: '',
    filters: [{ id: 1, mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }],
    logic: 'AND',
    sortBy: '',
    sortOrder: 'desc',
    limit: 100,
  })

  // Visual query state for report step editor (Phase 3)
  const [reportVisualMode, setReportVisualMode] = useState(false)
  const [reportVisualQuery, setReportVisualQuery] = useState<VisualQuery>({
    table: '',
    filters: [{ id: 1, mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }],
    logic: 'AND',
    sortBy: '',
    sortOrder: 'desc',
    limit: 100,
  })

  // Initialize the draft from the loaded workflow
  useEffect(() => {
    if (workflow?.steps) {
      setDraftSteps(workflow.steps)
      setConfigDraft(workflow.config || {})
      setDeletedStepIds([])
      setIsDirty(false)
      setSaveError('')
      setSavedMessage('')
    }
  }, [workflow])

  const [showStartConfig, setShowStartConfig] = useState(false)
  const [startStepIds, setStartStepIds] = useState<number[]>([])

  // Marketplace / My Nodes state
  const [showSaveNodeModal, setShowSaveNodeModal] = useState<'marketplace' | 'my-nodes' | null>(null)
  const [saveNodeForm, setSaveNodeForm] = useState({
    name: '',
    description: '',
    category: 'General',
    tags: '',
    title: '',
  })
  const [saveNodeError, setSaveNodeError] = useState('')
  const [saveNodeSuccess, setSaveNodeSuccess] = useState(false)
  const [showMyNodesPanel, setShowMyNodesPanel] = useState(false)

  const buildGraph = useCallback(() => {
    const steps = draftSteps
    const newNodes: Node[] = []
    const newEdges: Edge[] = []
    const stepMap = new Map(steps.map(s => [s.id, s]))

    // Build lookup maps for resolving user/group names on nodes
    const userLookup = new Map<number, string>()
    users?.forEach(u => userLookup.set(u.id, u.full_name || u.username))
    const groupLookup = new Map<number, string>()
    groups?.forEach(g => groupLookup.set(g.id, g.name))

    const startPos = nodePositions.current['start'] || { x: 250, y: 0 }
    newNodes.push({
      id: 'start',
      type: 'start',
      position: startPos,
      data: { label: 'Start', startStepIds: configDraft?.start_step_ids || [] }
    })

    steps.forEach((step, index) => {
      const routes = step.step_type === 'condition' ? (step.definition?.routes || []) : undefined
      const savedPos = step.definition?.pos_x != null ? { x: step.definition.pos_x, y: step.definition.pos_y } : null
      const movedPos = nodePositions.current[`step-${step.id}`]
      const def = step.definition || {}
      // Resolve user/group names for display on nodes
      const assignedUserName = def.assigned_to_user_id ? (userLookup.get(def.assigned_to_user_id) || `User #${def.assigned_to_user_id}`) : null
      const assignedGroupName = def.assigned_group_id ? (groupLookup.get(def.assigned_group_id) || `Group #${def.assigned_group_id}`) : null
      newNodes.push({
        id: `step-${step.id}`,
        type: stepTypeToNodeType(step.step_type),
        position: savedPos || movedPos || { x: 250, y: 100 + (index * 140) },
        data: {
          stepId: step.id,
          label: step.step_type,
          title: step.title || '',
          description: step.description || '',
          ...def,
          condition_expr: step.condition_expr,
          routes,
          assigned_user_name: assignedUserName,
          assigned_group_name: assignedGroupName
        }
      })
    })

    // Build edges from step definitions — connections are drawn ONLY from node settings
    const addEdgeFor = (stepId: number, sourceHandle: string, target: string | number, label: string, color: string) => {
      const targetId = target === END_TARGET ? 'end' : `step-${target}`
      newEdges.push({
        id: `e-${stepId}-${sourceHandle}`,
        source: `step-${stepId}`,
        sourceHandle,
        target: targetId,
        animated: true,
        label,
        ...edgeColor(color)
      })
    }

    steps.forEach(step => {
      const def = step.definition || {}
      if (step.step_type === 'condition') {
        const routes = def.routes || []
        routes.forEach((route: any, i: number) => {
          if (route.target_step_id && (route.target_step_id === END_TARGET || stepMap.has(route.target_step_id))) {
            addEdgeFor(step.id, `route-${i}`, route.target_step_id, route.expression || `Route ${i + 1}`, '#27ae60')
          }
        })
        if (def.default_target_step_id && (def.default_target_step_id === END_TARGET || stepMap.has(def.default_target_step_id))) {
          addEdgeFor(step.id, 'default', def.default_target_step_id, 'Else', '#e74c3c')
        }
      } else {
        const targets = def.next_step_ids || (def.next_step_id ? [def.next_step_id] : [])
        targets.forEach((targetId: number, i: number) => {
          if (targetId && (targetId === END_TARGET || stepMap.has(targetId))) {
            addEdgeFor(step.id, `out-${i}`, targetId, targetId === END_TARGET ? 'End' : '', '#1565c0')
          }
        })
      }
    })

    // Start node → explicitly configured outputs only (no auto-derived connections)
    const startIds: number[] = (configDraft?.start_step_ids || [])
      .filter((sid: number) => stepMap.has(sid))
    startIds.forEach((sid, i) => {
      newEdges.push({
        id: `e-start-${sid}`,
        source: 'start',
        sourceHandle: `start-out-${i}`,
        target: `step-${sid}`,
        animated: true,
        style: { ...edgeBase.style, stroke: '#27ae60' },
        markerEnd: { ...edgeBase.markerEnd, color: '#27ae60' }
      })
    })

    const endPos = nodePositions.current['end'] || { x: 250, y: 100 + ((steps.length || 1) * 140) }
    newNodes.push({
      id: 'end',
      type: 'end',
      position: endPos,
      data: { label: 'End' }
    })

    setNodes(newNodes)
    setEdges(newEdges)
  }, [draftSteps, configDraft, users, groups])

  useEffect(() => {
    buildGraph()
  }, [buildGraph])

  const handleNodesChange = useCallback((changes: any[]) => {
    setNodes((nds) => {
      return produce(nds, (draft) => {
        changes.forEach(change => {
          if (change.type === 'position' && change.position) {
            const node = draft.find(n => n.id === change.id)
            if (node) {
              node.position = change.position
            }
          }
        })
      })
    })
  }, [])

  const handleNodeDragStop = useCallback((_: any, node: Node) => {
    nodePositions.current[node.id] = { ...node.position }
    const stepId = parseInt((node.id as string).replace('step-', ''))
    if (!isNaN(stepId)) {
      setDraftSteps(prev => prev.map(s => {
        if (s.id !== stepId) return s
        return {
          ...s,
          definition: { ...s.definition, pos_x: node.position.x, pos_y: node.position.y }
        }
      }))
      setIsDirty(true)
    }
  }, [])

  const handleNodeClick = (nodeId: string) => {
    if (nodeId === 'start') {
      setStartStepIds([...(configDraft?.start_step_ids || [])])
      setShowStartConfig(true)
      setShowAddStep(false)
      return
    }
    if (!nodeId.startsWith('step-')) return
    const stepId = parseInt(nodeId.replace('step-', ''))
    const step = draftSteps.find((s: any) => s.id === stepId)
    if (step) {
      setSelectedStep(step)
      setEditingDef({ ...step.definition })
      setEditingTitle(step.title || '')
      setEditingDescription(step.description || '')
      setShowAddStep(false)
      setNodeAiPanelOpen(false)
      setNodeAiResponse(null)
      setNodeAiError('')
      setNodeAiPrompt('')
      // Initialize visual query mode for database_query steps
      if (step.step_type === 'database_query') {
        const def = step.definition || {}
        if (def.visual_query) {
          setDbVisualMode(true)
          setDbVisualQuery(def.visual_query)
        } else {
          setDbVisualMode(false)
          setDbVisualQuery({
            table: def.table || '',
            filters: [{ id: 1, mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }],
            logic: 'AND',
            sortBy: '',
            sortOrder: 'desc',
            limit: 100,
          })
        }
      }
      // Initialize visual query mode for report steps (Phase 3)
      if (step.step_type === 'report' && step.definition?.report_type === 'sql_query') {
        const def = step.definition || {}
        if (def.visual_query) {
          setReportVisualMode(true)
          setReportVisualQuery(def.visual_query)
        } else {
          setReportVisualMode(false)
          setReportVisualQuery({
            table: '',
            filters: [{ id: 1, mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }],
            logic: 'AND',
            sortBy: '',
            sortOrder: 'desc',
            limit: def.sql_limit || 100,
          })
        }
      }
    }
  }

  const handleSaveStartConfig = () => {
    setConfigDraft((prev: any) => ({ ...(prev || {}), start_step_ids: startStepIds }))
    setShowStartConfig(false)
    setIsDirty(true)
  }

  // Save node to My Nodes library
  const handleSaveToMyNodes = async () => {
    if (!selectedStep) return
    setSaveNodeError('')
    setSaveNodeSuccess(false)
    try {
      await marketplaceApi.saveNode({
        step_type: selectedStep.step_type,
        title: saveNodeForm.title || selectedStep.title || `${selectedStep.step_type} node`,
        description: saveNodeForm.description || selectedStep.description || '',
        definition: editingDef,
        condition_expr: selectedStep.condition_expr || '',
        is_enabled: selectedStep.is_enabled,
        max_retries: selectedStep.max_retries || 0,
        retry_delay_seconds: selectedStep.retry_delay_seconds || 0,
        failure_hook_url: selectedStep.failure_hook_url || '',
      })
      setSaveNodeSuccess(true)
    } catch (err: any) {
      setSaveNodeError(err.response?.data?.detail || 'Failed to save node')
    }
  }

  // Save node to Marketplace
  const handleSaveToMarketplace = async () => {
    if (!selectedStep) return
    setSaveNodeError('')
    setSaveNodeSuccess(false)
    try {
      const nodeContent = JSON.stringify({
        step_type: selectedStep.step_type,
        title: saveNodeForm.title || selectedStep.title || `${selectedStep.step_type} node`,
        description: saveNodeForm.description || selectedStep.description || '',
        definition: editingDef,
        condition_expr: selectedStep.condition_expr || '',
        is_enabled: selectedStep.is_enabled,
        max_retries: selectedStep.max_retries || 0,
        retry_delay_seconds: selectedStep.retry_delay_seconds || 0,
        failure_hook_url: selectedStep.failure_hook_url || '',
      })
      const tagsArray = saveNodeForm.tags.split(',').map((t: string) => t.trim()).filter(Boolean)
      await marketplaceApi.createItem({
        item_type: 'node',
        name: saveNodeForm.name || saveNodeForm.title || selectedStep.title || `${selectedStep.step_type} node`,
        description: saveNodeForm.description || '',
        category: saveNodeForm.category,
        tags: tagsArray,
        content: nodeContent,
        content_format: 'json',
        node_type: selectedStep.step_type,
        status: 'published',
      })
      setSaveNodeSuccess(true)
    } catch (err: any) {
      setSaveNodeError(err.response?.data?.detail || 'Failed to publish node')
    }
  }

  // Insert a saved node from My Nodes into the workflow
  const handleInsertMyNode = (node: any) => {
    const tempId = -Date.now() - Math.floor(Math.random() * 100000)
    const newStep: WorkflowStep = {
      id: tempId,
      workflow_id: workflowId,
      step_type: node.step_type,
      definition: { ...node.definition },
      position: draftSteps.length,
      condition_expr: node.condition_expr || '',
      is_enabled: node.is_enabled !== false,
      title: node.title || '',
      description: node.description || '',
      max_retries: node.max_retries || 0,
      retry_delay_seconds: node.retry_delay_seconds || 0,
      failure_hook_url: node.failure_hook_url || '',
    }
    setDraftSteps(prev => [...prev, newStep])
    setShowMyNodesPanel(false)
    setIsDirty(true)
    requestAnimationFrame(() => {
      reactFlowInstance.current?.fitView({ padding: 1.5 })
    })
  }

  const handleAddStep = (stepType: string, definition: any) => {
    const tempId = -Date.now() - Math.floor(Math.random() * 100000)
    const newStep: WorkflowStep = {
      id: tempId,
      workflow_id: workflowId,
      step_type: stepType,
      definition,
      position: draftSteps.length,
      condition_expr: '',
      is_enabled: true,
      title: '',
      description: ''
    }
    setDraftSteps(prev => [...prev, newStep])
    setShowAddStep(false)
    setIsDirty(true)
    requestAnimationFrame(() => {
      reactFlowInstance.current?.fitView({ padding: 1.5 })
    })
  }

  const handleUpdateStepField = (key: string, value: any) => {
    setEditingDef((prev: any) => ({ ...prev, [key]: value }))
  }

  const handleSaveStep = () => {
    if (!selectedStep) return
    const def = { ...editingDef }
    if (Array.isArray(def.next_step_ids)) {
      def.next_step_ids = def.next_step_ids.filter((t: any) => t)
    }
    setDraftSteps(prev => prev.map(s =>
      s.id === selectedStep.id
        ? {
            ...s,
            definition: def,
            // P4.1: condition_expr is legacy; only keep for non-condition steps
            condition_expr: s.step_type === 'condition' ? '' : (s.condition_expr || ''),
            title: editingTitle,
            description: editingDescription
          }
        : s
    ))
    setSelectedStep(null)
    setIsDirty(true)
  }

  const handleDeleteStep = () => {
    if (!selectedStep) return
    const stepId = selectedStep.id
    if (!confirm(`Delete step "${selectedStep.step_type}"?`)) return

    setDraftSteps(prev => prev.map(s => {
      if (s.id === stepId) return s
      const def = { ...s.definition }
      if (Array.isArray(def.next_step_ids)) {
        def.next_step_ids = def.next_step_ids.filter((t: any) => t !== stepId)
      }
      if (def.next_step_id === stepId) delete def.next_step_id
      if (Array.isArray(def.routes)) {
        def.routes = def.routes.map((r: any) => r.target_step_id === stepId ? { ...r, target_step_id: null } : r)
      }
      if (def.default_target_step_id === stepId) def.default_target_step_id = null
      return { ...s, definition: def }
    }))
    setDraftSteps(prev => prev.filter(s => s.id !== stepId))
    setConfigDraft((prev: any) => ({
      ...(prev || {}),
      start_step_ids: ((prev || {}).start_step_ids || []).filter((sid: number) => sid !== stepId)
    }))
    if (stepId > 0) {
      setDeletedStepIds(prev => prev.includes(stepId) ? prev : [...prev, stepId])
    }
    setSelectedStep(null)
    setIsDirty(true)
  }

  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) return
    setAiLoading(true)
    setAiError('')
    try {
      const token = localStorage.getItem('token')
      const response = await axios.post(`${API_URL}/ai/generate-step`, null, {
        params: { description: aiPrompt },
        headers: { Authorization: `Bearer ${token}` }
      })
      const result = response.data
      if (result.success && result.step) {
        await handleAddStep(result.step.step_type, result.step.definition || {})
        setAiPrompt('')
      } else {
        setAiError('AI returned an empty step')
      }
    } catch (err: any) {
      setAiError(err.response?.data?.detail || 'AI generation failed')
    } finally {
      setAiLoading(false)
    }
  }

  // Per-node AI assist handlers
  const handleNodeAiAssist = async (action: string) => {
    if (!selectedStep) return
    if (action === 'generate' && !nodeAiPrompt.trim()) return

    setNodeAiLoading(true)
    setNodeAiError('')
    setNodeAiResponse(null)

    try {
      const body: any = {
        action,
        step_type: selectedStep.step_type,
      }
      if (action === 'generate') {
        body.description = nodeAiPrompt
      } else {
        body.current_config = editingDef
      }

      const res = await aiApi.assistNode(body)
      setNodeAiResponse(res.data.result)
    } catch (err: any) {
      setNodeAiError(err.response?.data?.detail || 'AI assist failed')
    } finally {
      setNodeAiLoading(false)
    }
  }

  const applyNodeAiConfig = () => {
    if (!nodeAiResponse) return
    const config = nodeAiResponse.config || nodeAiResponse.result?.fixed_config || nodeAiResponse.result?.optimized_config
    if (config && typeof config === 'object') {
      setEditingDef((prev: any) => ({ ...prev, ...config }))
      setNodeAiPanelOpen(false)
      setNodeAiResponse(null)
    }
  }

  const renderNodeAiPanel = () => {
    if (!selectedStep || !nodeAiPanelOpen) return null

    return (
      <div style={{ marginBottom: '1rem', padding: '0.75rem', background: '#fef9e7', borderRadius: '6px', border: '1px solid #f9e79f' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <strong>AI Assist — {selectedStep.step_type}</strong>
          <button className="btn btn-sm btn-secondary" onClick={() => { setNodeAiPanelOpen(false); setNodeAiResponse(null); setNodeAiError('') }}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <input
            className="form-input"
            type="text"
            value={nodeAiPrompt}
            onChange={(e) => setNodeAiPrompt(e.target.value)}
            placeholder="Describe what you need..."
            style={{ flex: 1 }}
          />
          <button
            className="btn btn-warning btn-sm"
            onClick={() => handleNodeAiAssist('generate')}
            disabled={nodeAiLoading || !nodeAiPrompt.trim()}
          >
            {nodeAiLoading ? '...' : 'Generate'}
          </button>
          <button
            className="btn btn-info btn-sm"
            onClick={() => handleNodeAiAssist('explain')}
            disabled={nodeAiLoading}
          >
            {nodeAiLoading ? '...' : 'Explain'}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => handleNodeAiAssist('optimize')}
            disabled={nodeAiLoading}
          >
            {nodeAiLoading ? '...' : 'Optimize'}
          </button>
        </div>

        {nodeAiError && <div className="error" style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>{nodeAiError}</div>}

        {nodeAiResponse && (
          <div style={{ padding: '0.75rem', background: '#fff', borderRadius: '4px', border: '1px solid #ddd', fontSize: '0.85rem' }}>
            {nodeAiResponse.action === 'generate' && nodeAiResponse.config && (
              <div>
                <strong>Generated Configuration:</strong>
                <pre style={{ whiteSpace: 'pre-wrap', marginTop: '0.5rem', background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px' }}>
                  {JSON.stringify(nodeAiResponse.config, null, 2)}
                </pre>
                <button className="btn btn-sm btn-success" style={{ marginTop: '0.5rem' }} onClick={applyNodeAiConfig}>
                  Apply to Node
                </button>
              </div>
            )}
            {nodeAiResponse.action === 'explain' && nodeAiResponse.result && (
              <div>
                <strong>Explanation:</strong>
                <p style={{ marginTop: '0.5rem' }}>{nodeAiResponse.result.explanation || JSON.stringify(nodeAiResponse.result)}</p>
                {nodeAiResponse.result.variables_used?.length > 0 && (
                  <div>
                    <strong>Variables used:</strong> {nodeAiResponse.result.variables_used.join(', ')}
                  </div>
                )}
              </div>
            )}
            {nodeAiResponse.action === 'fix' && nodeAiResponse.result && (
              <div>
                <strong>Fix:</strong>
                <p style={{ marginTop: '0.5rem' }}>{nodeAiResponse.result.explanation || ''}</p>
                {nodeAiResponse.result.fixed_config && (
                  <>
                    <pre style={{ whiteSpace: 'pre-wrap', background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px' }}>
                      {JSON.stringify(nodeAiResponse.result.fixed_config, null, 2)}
                    </pre>
                    <button className="btn btn-sm btn-success" style={{ marginTop: '0.5rem' }} onClick={applyNodeAiConfig}>
                      Apply Fix
                    </button>
                  </>
                )}
              </div>
            )}
            {nodeAiResponse.action === 'optimize' && nodeAiResponse.result && (
              <div>
                <strong>Optimization Suggestions:</strong>
                <ul style={{ marginTop: '0.5rem' }}>
                  {(nodeAiResponse.result.suggestions || []).map((s: string, i: number) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
                {nodeAiResponse.result.benefits && <p><strong>Benefits:</strong> {nodeAiResponse.result.benefits}</p>}
                {nodeAiResponse.result.optimized_config && (
                  <>
                    <pre style={{ whiteSpace: 'pre-wrap', background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px' }}>
                      {JSON.stringify(nodeAiResponse.result.optimized_config, null, 2)}
                    </pre>
                    <button className="btn btn-sm btn-success" style={{ marginTop: '0.5rem' }} onClick={applyNodeAiConfig}>
                      Apply Optimization
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  const addRoute = () => {
    const routes = [...(editingDef.routes || []), { expression: '', target_step_id: null }]
    setEditingDef((prev: any) => ({ ...prev, routes }))
  }

  const removeRoute = (idx: number) => {
    const routes = (editingDef.routes || []).filter((_: any, i: number) => i !== idx)
    setEditingDef((prev: any) => ({ ...prev, routes }))
  }

  const updateRoute = (idx: number, field: string, value: any) => {
    const routes = [...(editingDef.routes || [])]
    routes[idx] = { ...routes[idx], [field]: value }
    setEditingDef((prev: any) => ({ ...prev, routes }))
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveError('')
    setSavedMessage('')
    try {
      const idMap = new Map<number, number>()

      // 1. Persist brand-new steps first so we know their real ids
      for (const step of draftSteps) {
        if (step.id > 0) continue
        const res = await workflowApi.addStep(workflowId, {
          step_type: step.step_type,
          definition: step.definition,
          position: step.position,
          condition_expr: step.condition_expr,
          is_enabled: step.is_enabled,
          title: step.title || '',
          description: step.description || ''
        })
        idMap.set(step.id, res.data.id)
      }

      // 2. Remap temporary ids to real ids inside step definitions
      const remap = (def: any): any => {
        if (!def || typeof def !== 'object') return def
        const d = { ...def }
        if (Array.isArray(d.next_step_ids)) {
          d.next_step_ids = d.next_step_ids.map((t: any) => idMap.has(t) ? idMap.get(t) : t)
        }
        if (d.next_step_id != null && idMap.has(d.next_step_id)) d.next_step_id = idMap.get(d.next_step_id)
        if (Array.isArray(d.routes)) {
          d.routes = d.routes.map((r: any) => ({
            ...r,
            target_step_id: r.target_step_id != null && idMap.has(r.target_step_id)
              ? idMap.get(r.target_step_id)
              : r.target_step_id
          }))
        }
        if (d.default_target_step_id != null && idMap.has(d.default_target_step_id)) {
          d.default_target_step_id = idMap.get(d.default_target_step_id)
        }
        return d
      }

      // 3. Persist every step with its final (remapped) definition
      for (const step of draftSteps) {
        const realId = step.id > 0 ? step.id : idMap.get(step.id)
        if (realId == null) continue
        await workflowApi.updateStep(workflowId, realId, {
          definition: remap(step.definition),
          condition_expr: step.condition_expr,
          is_enabled: step.is_enabled,
          position: step.position,
          title: step.title || '',
          description: step.description || ''
        })
      }

      // 4. Remove deleted steps
      for (const stepId of deletedStepIds) {
        await workflowApi.deleteStep(workflowId, stepId)
      }

      // 5. Persist workflow config (start node outputs)
      const cfg = {
        ...(configDraft || {}),
        start_step_ids: ((configDraft || {}).start_step_ids || []).map(
          (sid: number) => idMap.has(sid) ? idMap.get(sid) : sid
        )
      }
      await workflowApi.update(workflowId, { config: cfg })

      await queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      setDeletedStepIds([])
      setIsDirty(false)
      setSavedMessage('Workflow saved successfully')
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || err.message || 'Failed to save workflow')
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    if (isDirty && !confirm('Discard unsaved changes?')) return
    navigate(`/workflows/${workflowId}`)
  }

  const renderStepEditor = () => {
    if (!selectedStep) return null

    const st = selectedStep.step_type

    const connectionSection = () => {
      if (st === 'condition' || st === 'start' || st === 'end') return null

      const targets: (number | null)[] = editingDef?.next_step_ids ||
        (editingDef?.next_step_id ? [editingDef.next_step_id] : [])

      const updateTargets = (updated: (number | null)[]) => {
        setEditingDef((prev: any) => {
          const next = { ...prev, next_step_ids: updated }
          delete next.next_step_id
          return next
        })
      }

      return (
        <div className="form-group" style={{ marginBottom: '1rem', padding: '0.75rem', background: '#f0f4f8', borderRadius: '6px' }}>
          <label className="form-label" style={{ fontWeight: 'bold' }}>
            Outputs (run in parallel after completion)
          </label>
          {targets.map((targetId, i) => (
            <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
              <span style={{ minWidth: '20px', fontSize: '0.8rem', color: '#7f8c8d' }}>{i + 1}.</span>
              <select className="form-select"
                value={targetId || ''}
                onChange={(e) => {
                  const val = e.target.value ? Number(e.target.value) : null
                  const updated = [...targets]
                  updated[i] = val as any
                  updateTargets(updated)
                }}
                style={{ flex: 1 }}>
                <option value="">-- Disconnected --</option>
                <option value={END_TARGET}>■ End (stop here)</option>
                {draftSteps
                  ?.filter((s: any) => s.id !== selectedStep.id)
                  .map((s: any) => (
                    <option key={s.id} value={s.id}>
                      [{s.id}] {s.title || s.step_type}{s.definition?.name ? ` - ${s.definition.name}` : ''}
                    </option>
                  ))}
              </select>
              <button className="btn btn-sm btn-danger" title="Remove output"
                onClick={() => updateTargets(targets.filter((_, idx) => idx !== i))}>
                ✕
              </button>
            </div>
          ))}
          <button className="btn btn-sm btn-primary" onClick={() => updateTargets([...targets, null])}>
            + Add Output
          </button>
        </div>
      )
    }

    const editorFields = () => {
      switch (st) {
        case 'api_call':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Method</label>
                <select className="form-select" value={editingDef.method || 'GET'}
                  onChange={(e) => handleUpdateStepField('method', e.target.value)}>
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                  <option value="DELETE">DELETE</option>
                  <option value="PATCH">PATCH</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">URL</label>
                <input className="form-input" type="text" value={editingDef.url || ''}
                  onChange={(e) => handleUpdateStepField('url', e.target.value)}
                  placeholder="https://api.example.com/endpoint" />
              </div>
              <div className="form-group">
                <label className="form-label">Headers (JSON)</label>
                <textarea className="form-textarea" rows={3}
                  value={typeof editingDef.headers === 'object' ? JSON.stringify(editingDef.headers, null, 2) : editingDef.headers || ''}
                  onChange={(e) => {
                    try { handleUpdateStepField('headers', JSON.parse(e.target.value)) }
                    catch { handleUpdateStepField('headers', e.target.value) }
                  }}
                  placeholder='{"Authorization": "Bearer ..."}' />
              </div>
              <div className="form-group">
                <label className="form-label">Body (JSON)</label>
                <textarea className="form-textarea" rows={4}
                  value={typeof editingDef.body === 'object' ? JSON.stringify(editingDef.body, null, 2) : editingDef.body || ''}
                  onChange={(e) => {
                    try { handleUpdateStepField('body', JSON.parse(e.target.value)) }
                    catch { handleUpdateStepField('body', e.target.value) }
                  }}
                  placeholder='{"key": "value"}' />
              </div>
            </>
          )
        case 'database_query':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Query Type</label>
                <select className="form-select" value={editingDef.query_type || 'select'}
                  onChange={(e) => {
                    handleUpdateStepField('query_type', e.target.value)
                    if (e.target.value !== 'select') {
                      setDbVisualMode(false)
                    }
                  }}>
                  <option value="select">SELECT</option>
                  <option value="insert">INSERT</option>
                  <option value="update">UPDATE</option>
                  <option value="delete">DELETE</option>
                  <option value="upsert">UPSERT</option>
                </select>
              </div>

              {editingDef.query_type === 'select' && (
                <div className="form-group">
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={dbVisualMode}
                      onChange={(e) => setDbVisualMode(e.target.checked)}
                      style={{ width: '18px', height: '18px' }}
                    />
                    <span className="form-label" style={{ margin: 0 }}>Use Visual Query Builder</span>
                  </label>
                </div>
              )}

              {editingDef.query_type === 'select' && dbVisualMode ? (
                <div style={{ maxHeight: '400px', overflow: 'auto' }}>
                  <QueryBuilder
                    tables={dbTables || []}
                    value={dbVisualQuery}
                    onChange={(q) => {
                      setDbVisualQuery(q)
                      handleUpdateStepField('table', q.table)
                      handleUpdateStepField('visual_query', q)
                    }}
                  />
                </div>
              ) : (
                <>
                  <div className="form-group">
                    <label className="form-label">Table</label>
                    <input className="form-input" type="text" value={editingDef.table || ''}
                      onChange={(e) => handleUpdateStepField('table', e.target.value)}
                      placeholder="users" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Query / Condition</label>
                    <textarea className="form-textarea" rows={3} value={editingDef.query || ''}
                      onChange={(e) => handleUpdateStepField('query', e.target.value)}
                      placeholder="WHERE status = 'active'" />
                  </div>
                </>
              )}

              {(editingDef.query_type === 'insert' || editingDef.query_type === 'update' || editingDef.query_type === 'upsert') && (
                <div className="form-group">
                  <label className="form-label">Data (JSON)</label>
                  <textarea className="form-textarea" rows={4}
                    value={typeof editingDef.data === 'object' ? JSON.stringify(editingDef.data, null, 2) : editingDef.data || ''}
                    onChange={(e) => {
                      try { handleUpdateStepField('data', JSON.parse(e.target.value)) }
                      catch { handleUpdateStepField('data', e.target.value) }
                    }}
                    placeholder='{"name": "John", "email": "john@example.com"}' />
                </div>
              )}

              {(editingDef.query_type === 'update' || editingDef.query_type === 'delete') && (
                <div className="form-group">
                  <label className="form-label">Conditions (JSON)</label>
                  <textarea className="form-textarea" rows={3}
                    value={typeof editingDef.conditions === 'object' ? JSON.stringify(editingDef.conditions, null, 2) : editingDef.conditions || ''}
                    onChange={(e) => {
                      try { handleUpdateStepField('conditions', JSON.parse(e.target.value)) }
                      catch { handleUpdateStepField('conditions', e.target.value) }
                    }}
                    placeholder='{"id": 1}' />
                </div>
              )}
            </>
          )
        case 'email':
          return (
            <>
              <div className="form-group">
                <label className="form-label">To</label>
                <input className="form-input" type="text" value={editingDef.to || ''}
                  onChange={(e) => handleUpdateStepField('to', e.target.value)}
                  placeholder="user@example.com" />
              </div>
              <div className="form-group">
                <label className="form-label">Subject</label>
                <input className="form-input" type="text" value={editingDef.subject || ''}
                  onChange={(e) => handleUpdateStepField('subject', e.target.value)}
                  placeholder="Workflow Notification" />
              </div>
              <div className="form-group">
                <label className="form-label">Body</label>
                <textarea className="form-textarea" rows={4} value={editingDef.body || ''}
                  onChange={(e) => handleUpdateStepField('body', e.target.value)}
                  placeholder="Email body text..." />
              </div>
            </>
          )
        case 'condition':
          return (
            <>
              <div className="alert alert-info" style={{ marginBottom: '1rem', padding: '0.75rem', background: '#e3f2fd', borderRadius: '6px', fontSize: '0.85rem' }}>
                <strong>P1.1 Model B:</strong> Conditions use per-route expressions. Each route must have a non-empty Python expression evaluated against <code>data</code> (step input). Empty expressions will fail at runtime.
              </div>
              <div className="form-group">
                <label className="form-label">Routes (connect handles on the node to target steps)</label>
                {(editingDef.routes || []).map((route: any, i: number) => (
                  <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                    <span style={{ fontWeight: 'bold', minWidth: '60px', fontSize: '0.8rem' }}>Route {i + 1}:</span>
                    <input className="form-input" type="text" value={route.expression || ''}
                      onChange={(e) => updateRoute(i, 'expression', e.target.value)}
                      placeholder="e.g., data['amount'] > 100" 
                      style={{ flex: 1, borderColor: !route.expression ? '#e74c3c' : undefined }} />
                    {(!route.expression || route.expression.trim() === '') && (
                      <span style={{ color: '#e74c3c', fontSize: '0.75rem', minWidth: '80px' }}>⚠ Empty!</span>
                    )}
                    <select className="form-select"
                      value={route.target_step_id || ''}
                      onChange={(e) => updateRoute(i, 'target_step_id', e.target.value ? Number(e.target.value) : null)}
                      style={{ minWidth: '140px' }}>
                      <option value="">-- Select step --</option>
                      <option value={END_TARGET}>■ End (stop here)</option>
                      {draftSteps
                        ?.filter((s: any) => s.id !== selectedStep.id)
                        .map((s: any) => (
                          <option key={s.id} value={s.id}>
                            [{s.id}] {s.title || s.step_type}{s.definition?.name ? ` - ${s.definition.name}` : ''}
                          </option>
                        ))}
                    </select>
                    <button className="btn btn-sm btn-danger" onClick={() => removeRoute(i)}>×</button>
                  </div>
                ))}
                <button className="btn btn-sm btn-primary" onClick={addRoute}>+ Add Route</button>
              </div>
              <div className="form-group">
                <label className="form-label">Else (default) → Target Step</label>
                <select className="form-select"
                  value={editingDef.default_target_step_id || ''}
                  onChange={(e) => handleUpdateStepField('default_target_step_id', e.target.value ? Number(e.target.value) : null)}
                  style={{ width: '100%' }}>
                  <option value="">-- No default --</option>
                  <option value={END_TARGET}>■ End (stop here)</option>
                  {draftSteps
                    ?.filter((s: any) => s.id !== selectedStep.id)
                    .map((s: any) => (
                      <option key={s.id} value={s.id}>
                        [{s.id}] {s.title || s.step_type}{s.definition?.name ? ` - ${s.definition.name}` : ''}
                      </option>
                    ))}
                </select>
                <small style={{ color: '#666' }}>If no route matches, go here. Leave empty to stop the run.</small>
              </div>
            </>
          )
        case 'form':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Select Form</label>
                <select className="form-select" value={editingDef.form_id || ''}
                  onChange={(e) => {
                    const fid = Number(e.target.value)
                    const f = forms?.find(fm => fm.id === fid)
                    handleUpdateStepField('form_id', fid)
                    handleUpdateStepField('form_name', f?.name || '')
                  }}>
                  <option value="">-- Select form --</option>
                  {(forms || []).filter(f => f.is_published).map((f) => (
                    <option key={f.id} value={f.id}>{f.name}</option>
                  ))}
                </select>
                <small style={{ color: '#666' }}>Only published forms are available. Publish a form in the Form Designer to use it here.</small>
              </div>
            </>
          )
        case 'human_task':
        case 'approval':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Assign to User (optional)</label>
                <select className="form-select" value={editingDef.assigned_to_user_id || ''}
                  onChange={(e) => handleUpdateStepField('assigned_to_user_id', e.target.value ? Number(e.target.value) : null)}>
                  <option value="">-- Unassigned (anyone can take) --</option>
                  {(users || []).map((u: UserOption) => (
                    <option key={u.id} value={u.id}>{u.full_name || u.username} ({u.email})</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Assign to Group (optional)</label>
                <select className="form-select" value={editingDef.assigned_group_id || ''}
                  onChange={(e) => handleUpdateStepField('assigned_group_id', e.target.value ? Number(e.target.value) : null)}>
                  <option value="">-- No group --</option>
                  {(groups || []).map((g: GroupOption) => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </select>
                <small style={{ color: '#666' }}>When a group is assigned, any member of that group can take the task.</small>
              </div>
              <div className="form-group">
                <label className="form-label">Form (optional, for approval steps)</label>
                <select className="form-select" value={editingDef.form_id || ''}
                  onChange={(e) => {
                    const fid = Number(e.target.value)
                    const f = forms?.find(fm => fm.id === fid)
                    handleUpdateStepField('form_id', fid || null)
                    handleUpdateStepField('form_name', f?.name || '')
                  }}>
                  <option value="">-- No form --</option>
                  {(forms || []).filter(f => f.is_published).map((f) => (
                    <option key={f.id} value={f.id}>{f.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Task Description</label>
                <textarea className="form-textarea" rows={3} value={editingDef.description || ''}
                  onChange={(e) => handleUpdateStepField('description', e.target.value)}
                  placeholder="What action is required?" />
              </div>
              <div className="form-group">
                <label className="form-label">Task Data (JSON, optional)</label>
                <textarea className="form-textarea" rows={3}
                  value={typeof editingDef.task_data === 'object' ? JSON.stringify(editingDef.task_data, null, 2) : editingDef.task_data || ''}
                  onChange={(e) => {
                    try { handleUpdateStepField('task_data', JSON.parse(e.target.value)) }
                    catch { handleUpdateStepField('task_data', e.target.value) }
                  }}
                  placeholder='{"context": "some data"}' />
              </div>
            </>
          )
        case 'webhook':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Webhook URL</label>
                <input className="form-input" type="text" value={editingDef.url || ''}
                  onChange={(e) => handleUpdateStepField('url', e.target.value)}
                  placeholder="https://example.com/webhook" />
              </div>
              <div className="form-group">
                <label className="form-label">HTTP Method</label>
                <select className="form-select" value={editingDef.method || 'POST'}
                  onChange={(e) => handleUpdateStepField('method', e.target.value)}>
                  <option value="POST">POST</option>
                  <option value="GET">GET</option>
                  <option value="PUT">PUT</option>
                  <option value="PATCH">PATCH</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Timeout (seconds)</label>
                <input className="form-input" type="number" value={editingDef.timeout || 30}
                  onChange={(e) => handleUpdateStepField('timeout', Number(e.target.value))}
                  min={1} max={300} />
              </div>
            </>
          )
        case 'custom_code':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Python Code</label>
                <textarea className="form-textarea" rows={10}
                  value={editingDef.code || ''}
                  onChange={(e) => handleUpdateStepField('code', e.target.value)}
                  placeholder="# Access input_data, write to output dict&#10;output['result'] = input_data.get('value', 0) * 2"
                  style={{ fontFamily: 'monospace', fontSize: '0.85rem' }} />
                <small style={{ color: '#666' }}>Code runs in a sandboxed thread. Only <code>input_data</code> and <code>output</code> dict are available.</small>
              </div>
              <div className="form-group">
                <label className="form-label">Timeout (seconds)</label>
                <input className="form-input" type="number" value={editingDef.timeout || 30}
                  onChange={(e) => handleUpdateStepField('timeout', Number(e.target.value))}
                  min={1} max={300} />
              </div>
            </>
          )
        case 'calculation':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Calculation Expression</label>
                <input className="form-input" type="text" value={editingDef.expression || ''}
                  onChange={(e) => handleUpdateStepField('expression', e.target.value)}
                  placeholder="e.g., data['amount'] * 1.1" />
                <small style={{ color: '#666' }}>Python expression evaluated against step input data (accessible as <code>data</code>)</small>
              </div>
            </>
          )
        case 'report':
          return (
            <>
              <div className="form-group">
                <label className="form-label">Report Title</label>
                <input className="form-input" type="text" value={editingDef.title || ''}
                  onChange={(e) => handleUpdateStepField('title', e.target.value)}
                  placeholder="Monthly Sales Report" />
              </div>
              <div className="form-group">
                <label className="form-label">Report Type</label>
                <select className="form-select" value={editingDef.report_type || 'table'}
                  onChange={(e) => handleUpdateStepField('report_type', e.target.value)}>
                  <option value="table">Table</option>
                  <option value="graph">Graph/Chart</option>
                  <option value="readonly_form">Read-only Form</option>
                  <option value="sql_query">SQL Query</option>
                </select>
              </div>
              {editingDef.report_type === 'sql_query' ? (
                <>
                  <div className="form-group">
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={reportVisualMode}
                        onChange={(e) => setReportVisualMode(e.target.checked)}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span className="form-label" style={{ margin: 0 }}>Use Visual Query Builder</span>
                    </label>
                  </div>

                  {reportVisualMode ? (
                    <div style={{ maxHeight: '400px', overflow: 'auto' }}>
                      <QueryBuilder
                        tables={dbTables || []}
                        value={reportVisualQuery}
                        onChange={(q) => {
                          setReportVisualQuery(q)
                          handleUpdateStepField('visual_query', q)
                          handleUpdateStepField('sql_limit', q.limit)
                        }}
                      />
                    </div>
                  ) : (
                    <>
                      <div className="form-group">
                        <label className="form-label">SQL Query</label>
                        <textarea className="form-textarea" rows={6} value={editingDef.sql_query || ''}
                          onChange={(e) => handleUpdateStepField('sql_query', e.target.value)}
                          placeholder="SELECT name, email FROM users WHERE status = 'active' ORDER BY name"
                          style={{ fontFamily: 'monospace', fontSize: '0.85rem' }} />
                        <small style={{ color: '#7f8c8d' }}>
                          SELECT queries only. Use $input.field_name to reference data from previous steps.
                        </small>
                      </div>
                      <div className="form-group">
                        <label className="form-label">Row Limit</label>
                        <input className="form-input" type="number" min={1} max={10000}
                          value={editingDef.sql_limit || 100}
                          onChange={(e) => handleUpdateStepField('sql_limit', parseInt(e.target.value) || 100)}
                          style={{ maxWidth: '200px' }} />
                      </div>
                    </>
                  )}
                </>
              ) : (
                <div className="form-group">
                  <label className="form-label">Data Source (step ID that provides data)</label>
                  <select className="form-select" value={editingDef.data_source_step_id || ''}
                    onChange={(e) => handleUpdateStepField('data_source_step_id', e.target.value ? Number(e.target.value) : null)}>
                    <option value="">-- Select step --</option>
                    {draftSteps
                      ?.filter((s: any) => s.id !== selectedStep?.id)
                      .map((s: any) => (
                        <option key={s.id} value={s.id}>
                          [{s.id}] {s.title || s.step_type}
                        </option>
                      ))}
                  </select>
                </div>
              )}
            </>
          )
        default:
          return (
            <div className="form-group">
              <label className="form-label">Definition (JSON)</label>
              <textarea className="form-textarea" rows={8}
                value={JSON.stringify(editingDef, null, 2)}
                onChange={(e) => {
                  try { setEditingDef(JSON.parse(e.target.value)) }
                  catch { }
                }} />
            </div>
          )
      }
    }

    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.4)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000
      }} onClick={() => setSelectedStep(null)}>
        <div className="card" style={{
          maxWidth: '600px', width: '90%', maxHeight: '80vh', overflow: 'auto',
          border: '2px solid #3498db', padding: '1.5rem'
        }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 className="card-title" style={{ margin: 0 }}>Edit Step: {selectedStep.step_type}</h3>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className={`btn btn-sm ${nodeAiPanelOpen ? 'btn-warning' : 'btn-secondary'}`}
                onClick={() => setNodeAiPanelOpen(!nodeAiPanelOpen)}
              >
                AI Assist
              </button>
              <button
                className="btn btn-sm btn-info"
                onClick={() => {
                  setSaveNodeForm({
                    name: selectedStep.title || `${selectedStep.step_type} node`,
                    description: selectedStep.description || '',
                    category: 'General',
                    tags: '',
                    title: selectedStep.title || '',
                  })
                  setSaveNodeError('')
                  setSaveNodeSuccess(false)
                  setShowSaveNodeModal('my-nodes')
                }}
                title="Save this node config to your personal library"
              >
                Save to My Nodes
              </button>
              <button
                className="btn btn-sm btn-success"
                onClick={() => {
                  setSaveNodeForm({
                    name: selectedStep.title || `${selectedStep.step_type} node`,
                    description: selectedStep.description || '',
                    category: 'General',
                    tags: '',
                    title: selectedStep.title || '',
                  })
                  setSaveNodeError('')
                  setSaveNodeSuccess(false)
                  setShowSaveNodeModal('marketplace')
                }}
                title="Publish this node config to the marketplace"
              >
                ⊕ Marketplace
              </button>
              <button className="btn btn-sm btn-danger" onClick={handleDeleteStep}>
                Delete Step
              </button>
            </div>
          </div>
          {renderNodeAiPanel()}
          {connectionSection()}
          
          {/* Step Title and Description */}
          <div className="form-group">
            <label className="form-label">Step Title (optional)</label>
            <input 
              className="form-input" 
              type="text" 
              value={editingTitle}
              onChange={(e) => setEditingTitle(e.target.value)}
              placeholder="e.g., Wait for approval"
            />
          </div>
          
          <div className="form-group">
            <label className="form-label">Description (optional)</label>
            <textarea 
              className="form-textarea" 
              rows={2}
              value={editingDescription}
              onChange={(e) => setEditingDescription(e.target.value)}
              placeholder="What this step does..."
            />
          </div>
          
          {editorFields()}
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button className="btn btn-success" onClick={handleSaveStep}>
              Save Changes
            </button>
            <button className="btn btn-secondary" onClick={() => setSelectedStep(null)}>
              Cancel
            </button>
          </div>
          <small style={{ display: 'block', marginTop: '0.5rem', color: '#7f8c8d' }}>
            Changes are staged in the editor. Use "Save Workflow" to persist all changes, or "Cancel" to discard.
          </small>
        </div>
      </div>
    )
  }

  const renderStartConfig = () => {
    if (!showStartConfig) return null
    const steps = draftSteps
    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.4)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000
      }} onClick={() => setShowStartConfig(false)}>
        <div className="card" style={{
          maxWidth: '500px', width: '90%',
          border: '2px solid #27ae60', padding: '1.5rem'
        }} onClick={(e) => e.stopPropagation()}>
          <h3 className="card-title" style={{ margin: '0 0 0.5rem 0' }}>Start Node: Outputs</h3>
          <p style={{ color: '#666', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
            Choose which step(s) run in parallel when the workflow is triggered.
          </p>
          {steps.length === 0 && (
            <div className="error">Add a step first before configuring the start node.</div>
          )}
          {steps.map((s: any) => (
            <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 0', cursor: 'pointer' }}>
              <input type="checkbox"
                checked={startStepIds.includes(s.id)}
                onChange={(e) => {
                  if (e.target.checked) {
                    setStartStepIds(prev => [...prev, s.id])
                  } else {
                    setStartStepIds(prev => prev.filter(id => id !== s.id))
                  }
                }} />
              <span>[{s.id}] {s.title || s.step_type}{s.definition?.name ? ` - ${s.definition.name}` : ''}</span>
            </label>
          ))}
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button className="btn btn-success" onClick={handleSaveStartConfig}>
              Save
            </button>
            <button className="btn btn-secondary" onClick={() => setShowStartConfig(false)}>
              Cancel
            </button>
          </div>
          <small style={{ display: 'block', marginTop: '0.5rem', color: '#7f8c8d' }}>
            Changes are staged. Use "Save Workflow" to persist.
          </small>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return <div className="loading">Loading workflow...</div>
  }

  return (
    <ReactFlowProvider>
      <div>
        <div className="card-header">
        <div>
          <h2>Design Workflow: {(workflow as any)?.name || 'Loading...'}</h2>
          <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>
            Click a node to edit its settings and connections. Lines show what each step outputs to.
          </p>
          {isDirty && !saving && (
            <p style={{ color: '#b9770e', marginTop: '0.25rem', fontSize: '0.85rem' }}>
              Unsaved changes — click "Save Workflow" to persist or "Cancel" to discard.
            </p>
          )}
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={() => setShowAddStep(!showAddStep)}>
            + Add Step
          </button>
          <button className="btn btn-info" onClick={() => setShowMyNodesPanel(!showMyNodesPanel)}>
            {showMyNodesPanel ? 'Hide' : 'My'} Nodes Library
          </button>
          <button className="btn btn-success" onClick={handleSave} disabled={saving || !isDirty}>
            {saving ? 'Saving...' : 'Save Workflow'}
          </button>
          <button className="btn btn-secondary" onClick={handleCancel}>
            {isDirty ? 'Cancel' : 'Back'}
          </button>
        </div>
      </div>

      {saveError && <div className="error" style={{ marginBottom: '0.5rem' }}>{saveError}</div>}
      {savedMessage && <div className="success" style={{ marginBottom: '0.5rem' }}>{savedMessage}</div>}

      {showAddStep && (
        <div className="card">
          <h3 className="card-title">Add New Step</h3>

          {aiError && <div className="error" style={{ marginBottom: '0.5rem' }}>{aiError}</div>}

          <div style={{ marginBottom: '1rem', padding: '0.75rem', background: '#fef9e7', borderRadius: '6px', border: '1px solid #f9e79f' }}>
            <label className="form-label">AI Step Generator</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input className="form-input" type="text" value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="Describe the step you want to create..."
                style={{ flex: 1 }} />
              <button className="btn btn-warning" onClick={handleAiGenerate} disabled={aiLoading || !aiPrompt.trim()}>
                {aiLoading ? 'Generating...' : 'AI Assist'}
              </button>
            </div>
          </div>

          <p style={{ color: '#666', marginBottom: '0.75rem' }}>Or choose a step type:</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
            <button className="btn btn-primary" onClick={() => handleAddStep('api_call', { method: 'GET', url: '' })}>
              🌐 API Call
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('database_query', { type: 'select', table: '' })}>
              🗄️ Database Query
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('email', { to: '', subject: '', body: '' })}>
              📧 Email
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('condition', { routes: [{ expression: '', target_step_id: null }], default_target_step_id: null })}>
              ❓ Condition
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('form', { form_id: null })}>
              📝 Form
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('delay', { seconds: 0 })}>
              ⏱ Delay
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('human_task', { assigned_to_user_id: null, form_id: null })}>
              👤 Human Task
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('approval', { assigned_to_user_id: null, form_id: null })}>
              ✅ Approval
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('webhook', { url: '' })}>
              🔗 Webhook
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('custom_code', { code: '' })}>
              💻 Custom Code
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('calculation', { expression: '' })}>
              🧮 Calculation
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('report', { report_type: 'sql_query', title: '', sql_query: '', sql_limit: 100 })}>
              📊 Report
            </button>
          </div>
        </div>
      )}

      <CanvasFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onNodeDragStop={handleNodeDragStop}
        onNodeClick={(_, node) => handleNodeClick(node.id)}
        onNodesInitialized={(instance) => { reactFlowInstance.current = instance }}
      />

      {renderStepEditor()}
      {renderStartConfig()}

      {/* My Nodes Library Panel */}
      {showMyNodesPanel && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 className="card-title" style={{ margin: 0 }}>My Nodes Library</h3>
            <button className="btn btn-sm btn-secondary" onClick={() => setShowMyNodesPanel(false)}>✕ Close</button>
          </div>
          <p style={{ color: '#666', fontSize: '0.85rem', marginBottom: '1rem' }}>
            Click a node to insert it into the current workflow.
          </p>
          <MyNodesList onSelect={handleInsertMyNode} />
        </div>
      )}

      {/* Save Node Modal (My Nodes or Marketplace) */}
      {showSaveNodeModal && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1100
          }}
          onClick={() => setShowSaveNodeModal(null)}
        >
          <div
            className="card"
            style={{ maxWidth: '500px', width: '90%', maxHeight: '85vh', overflow: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 className="card-title" style={{ margin: 0 }}>
                {showSaveNodeModal === 'marketplace' ? 'Publish Node to Marketplace' : 'Save to My Nodes'}
              </h3>
              <button onClick={() => setShowSaveNodeModal(null)} style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#999' }}>&times;</button>
            </div>

            {saveNodeSuccess && (
              <div style={{ padding: '0.75rem', background: '#f0fff4', borderRadius: '6px', marginBottom: '1rem', color: '#27ae60' }}>
                {showSaveNodeModal === 'marketplace' ? 'Node published to marketplace!' : 'Node saved to your library!'}
              </div>
            )}

            {saveNodeError && (
              <div style={{ padding: '0.75rem', background: '#fdf2f2', borderRadius: '6px', marginBottom: '1rem', color: '#e74c3c' }}>
                {saveNodeError}
              </div>
            )}

            {!saveNodeSuccess && (
              <>
                <div className="form-group">
                  <label className="form-label">Title</label>
                  <input
                    className="form-input"
                    type="text"
                    value={saveNodeForm.title}
                    onChange={(e) => setSaveNodeForm({ ...saveNodeForm, title: e.target.value })}
                    placeholder="Node display name"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    className="form-textarea"
                    rows={2}
                    value={saveNodeForm.description}
                    onChange={(e) => setSaveNodeForm({ ...saveNodeForm, description: e.target.value })}
                    placeholder="What this node does..."
                  />
                </div>

                {showSaveNodeModal === 'marketplace' && (
                  <>
                    <div className="form-group">
                      <label className="form-label">Marketplace Name</label>
                      <input
                        className="form-input"
                        type="text"
                        value={saveNodeForm.name}
                        onChange={(e) => setSaveNodeForm({ ...saveNodeForm, name: e.target.value })}
                        placeholder="Public listing name"
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Category</label>
                      <select
                        className="form-select"
                        value={saveNodeForm.category}
                        onChange={(e) => setSaveNodeForm({ ...saveNodeForm, category: e.target.value })}
                      >
                        <option value="Data / ETL">Data / ETL</option>
                        <option value="Notifications">Notifications</option>
                        <option value="Approvals & Tasks">Approvals & Tasks</option>
                        <option value="Reporting">Reporting</option>
                        <option value="Integrations">Integrations</option>
                        <option value="Schedules & Maintenance">Schedules & Maintenance</option>
                        <option value="Onboarding">Onboarding</option>
                        <option value="General">General</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Tags (comma-separated)</label>
                      <input
                        className="form-input"
                        type="text"
                        value={saveNodeForm.tags}
                        onChange={(e) => setSaveNodeForm({ ...saveNodeForm, tags: e.target.value })}
                        placeholder="e.g., api, http, data"
                      />
                    </div>
                  </>
                )}

                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
                  <button
                    className="btn btn-success"
                    onClick={showSaveNodeModal === 'marketplace' ? handleSaveToMarketplace : handleSaveToMyNodes}
                  >
                    {showSaveNodeModal === 'marketplace' ? 'Publish to Marketplace' : 'Save to My Nodes'}
                  </button>
                  <button className="btn btn-secondary" onClick={() => setShowSaveNodeModal(null)}>Cancel</button>
                </div>
              </>
            )}

            {saveNodeSuccess && (
              <button className="btn btn-secondary" onClick={() => setShowSaveNodeModal(null)}>Close</button>
            )}
          </div>
        </div>
      )}
      </div>
    </ReactFlowProvider>
  )
}
