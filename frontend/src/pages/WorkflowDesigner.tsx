import React, { useState, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { produce } from 'immer'
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Connection,
  Panel
} from 'react-flow-renderer'
import { workflowApi } from '../services/api'
import 'react-flow-renderer/dist/style.css'

interface WorkflowStep {
  id: number
  step_type: string
  definition: any
  position: number
  condition_expr: string
  is_enabled: boolean
}

interface Workflow {
  id: number
  name: string
  steps: WorkflowStep[]
}

const nodeTypes = {
  apiCall: ({ data }: any) => (
    <div style={{ 
      background: '#e3f2fd', 
      border: '2px solid #1565c0',
      padding: '10px 20px',
      borderRadius: '8px',
      minWidth: '150px'
    }}>
      <strong>🌐 API Call</strong>
      <div style={{ fontSize: '0.75rem', marginTop: '5px' }}>{data.method || 'GET'}</div>
    </div>
  ),
  databaseQuery: ({ data }: any) => (
    <div style={{ 
      background: '#e8f5e9', 
      border: '2px solid #2e7d32',
      padding: '10px 20px',
      borderRadius: '8px',
      minWidth: '150px'
    }}>
      <strong>🗄️ Database</strong>
      <div style={{ fontSize: '0.75rem', marginTop: '5px' }}>{data.query_type || 'SELECT'}</div>
    </div>
  ),
  email: ({ data }: any) => (
    <div style={{ 
      background: '#fff3e0', 
      border: '2px solid #ef6c00',
      padding: '10px 20px',
      borderRadius: '8px',
      minWidth: '150px'
    }}>
      <strong>📧 Email</strong>
      <div style={{ fontSize: '0.75rem', marginTop: '5px' }}>{data.to || 'N/A'}</div>
    </div>
  ),
  condition: ({ data }: any) => (
    <div style={{ 
      background: '#fce4ec', 
      border: '2px solid #c2185b',
      padding: '10px 20px',
      borderRadius: '8px',
      minWidth: '150px'
    }}>
      <strong>❓ Condition</strong>
      <div style={{ fontSize: '0.75rem', marginTop: '5px' }}>{data.expression || ''}</div>
    </div>
  ),
  form: ({ data }: any) => (
    <div style={{ 
      background: '#f3e5f5', 
      border: '2px solid #7b1fa2',
      padding: '10px 20px',
      borderRadius: '8px',
      minWidth: '150px'
    }}>
      <strong>📝 Form</strong>
      <div style={{ fontSize: '0.75rem', marginTop: '5px' }}>{data.form_id || 'New Form'}</div>
    </div>
  ),
  start: ({ data }: any) => (
    <div style={{ 
      background: '#27ae60', 
      color: 'white',
      padding: '10px 20px',
      borderRadius: '20px',
      minWidth: '120px',
      textAlign: 'center'
    }}>
      <strong>▶ Start</strong>
    </div>
  ),
  end: ({ data }: any) => (
    <div style={{ 
      background: '#e74c3c', 
      color: 'white',
      padding: '10px 20px',
      borderRadius: '20px',
      minWidth: '120px',
      textAlign: 'center'
    }}>
      <strong>■ End</strong>
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

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: async () => {
      const response = await workflowApi.get(workflowId)
      return response.data as any
    },
    enabled: !!id
  })

  useEffect(() => {
    if (workflow?.steps) {
      convertStepsToNodes(workflow.steps)
    }
  }, [workflow])

  const updateMutation = useMutation({
    mutationFn: (data: any) => workflowApi.update(workflowId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
    }
  })

  const convertStepsToNodes = (steps: WorkflowStep[]) => {
    const newNodes: Node[] = []
    const newEdges: Edge[] = []

    // Add start node
    newNodes.push({
      id: 'start',
      type: 'start',
      position: { x: 250, y: 0 },
      data: { label: 'Start' }
    })

    // Add step nodes
    steps.forEach((step, index) => {
      newNodes.push({
        id: `step-${step.id}`,
        type: step.step_type,
        position: { x: 250, y: 100 + (index * 120) },
        data: { 
          label: step.step_type,
          ...step.definition 
        }
      })

      // Connect to previous node
      if (index === 0) {
        newEdges.push({
          id: `e-start-${step.id}`,
          source: 'start',
          target: `step-${step.id}`,
          animated: true
        })
      } else {
        newEdges.push({
          id: `e-${steps[index-1].id}-${step.id}`,
          source: `step-${steps[index-1].id}`,
          target: `step-${step.id}`,
          animated: true
        })
      }
    })

    // Add end node if there are steps
    if (steps.length > 0) {
      const lastStep = steps[steps.length - 1]
      newNodes.push({
        id: 'end',
        type: 'end',
        position: { x: 250, y: 100 + (steps.length * 120) },
        data: { label: 'End' }
      })

      newEdges.push({
        id: `e-${lastStep.id}-end`,
        source: `step-${lastStep.id}`,
        target: 'end',
        animated: true
      })
    }

    setNodes(newNodes)
    setEdges(newEdges)
  }

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    []
  )

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (node.id.startsWith('step-')) {
      const stepId = parseInt(node.id.replace('step-', ''))
      const step = workflow?.steps?.find((s: any) => s.id === stepId)
      if (step) {
        setSelectedStep(step)
        setShowAddStep(false)
      }
    }
  }, [workflow])

  const handleAddStep = async (stepType: string, definition: any) => {
    await workflowApi.addStep(workflowId, {
      step_type: stepType,
      definition,
      position: workflow?.steps?.length || 0
    })
    setShowAddStep(false)
    queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
  }

  const handleUpdateStep = async () => {
    if (selectedStep && workflow?.steps) {
      await workflowApi.update(workflowId, {
        steps: workflow.steps.map((s: any) => 
          s.id === selectedStep.id ? { ...s, definition: selectedStep.definition } : s
        )
      })
      setSelectedStep(null)
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
    }
  }

  if (isLoading) {
    return <div className="loading">Loading workflow...</div>
  }

  return (
    <div>
      <div className="card-header">
        <div>
          <h2>Design Workflow: {(workflow as any)?.name || 'Loading...'}</h2>
          <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>
            Visual workflow editor - drag nodes to rearrange
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button 
            className="btn btn-primary"
            onClick={() => setShowAddStep(!showAddStep)}
          >
            + Add Step
          </button>
          <Link to={`/workflows/${workflowId}`} className="btn btn-secondary">
            Back to Details
          </Link>
        </div>
      </div>

      {showAddStep && (
        <div className="card">
          <h3 className="card-title">Add New Step</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginTop: '1rem' }}>
            <button className="btn btn-primary" onClick={() => handleAddStep('api_call', { method: 'GET', url: '' })}>
              🌐 API Call
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('database_query', { query_type: 'select' })}>
              🗄️ Database Query
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('email', { to: '', subject: '' })}>
              📧 Email
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('condition', { expression: 'True' })}>
              ❓ Condition
            </button>
            <button className="btn btn-primary" onClick={() => handleAddStep('form', { form_id: '' })}>
              📝 Form
            </button>
          </div>
        </div>
      )}

      <div className="workflow-designer">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={(changes) => {
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
          }}
          onEdgesChange={() => {}}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
        >
          <Background />
          <Controls />
          <MiniMap />
          <Panel position="top-right">
            <div style={{ background: 'white', padding: '10px', borderRadius: '4px' }}>
              <small>{nodes.length - 2} steps</small>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      {selectedStep && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3 className="card-title">Edit Step: {selectedStep.step_type}</h3>
          <div className="form-group">
            <label className="form-label">Definition (JSON)</label>
            <textarea
              className="form-textarea"
              value={JSON.stringify(selectedStep.definition, null, 2)}
              onChange={(e) => setSelectedStep({...selectedStep, definition: JSON.parse(e.target.value)})}
              rows={10}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Condition Expression (optional)</label>
            <input
              type="text"
              className="form-input"
              value={selectedStep.condition_expr}
              onChange={(e) => setSelectedStep({...selectedStep, condition_expr: e.target.value})}
              placeholder="e.g., data.get('status') == 'active'"
            />
          </div>
          <button className="btn btn-success" onClick={handleUpdateStep}>
            Save Changes
          </button>
        </div>
      )}
    </div>
  )
}
