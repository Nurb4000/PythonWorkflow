/**
 * CMDB Relationships UI — view/edit relationships between configuration items.
 * 
 * Backend endpoints:
 *   GET /cmdb/items/{id}/relationships
 *   POST /cmdb/relationships
 *   DELETE /cmdb/relationships/{id}
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { cmdbApi } from '../services/api'

interface Relationship {
  id: number
  source_ci_id: number
  target_ci_id: number
  relationship_type: string
  properties: Record<string, any>
  is_active: boolean
  source_name?: string
  target_name?: string
  source_type_name?: string
  target_type_name?: string
}

const RELATIONSHIP_TYPES = [
  'depends_on',
  'connects_to',
  'manages',
  'monitors',
  'backed_up_by',
  'contained_in',
  'installed_on',
  'version_of',
  'component_of',
  'uses',
  'provides',
  'other'
]

export const CIRelationships: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const itemId = parseInt(id!)
  const queryClient = useQueryClient()
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newRelType, setNewRelType] = useState('depends_on')
  const [newTargetId, setNewTargetId] = useState('')
  const [newProperties, setNewProperties] = useState('')

  const { data: relationships, isLoading } = useQuery({
    queryKey: ['ci-relationships', itemId],
    queryFn: async () => {
      const res = await cmdbApi.getItemRelationships(itemId)
      return res.data as Relationship[]
    },
    enabled: !!itemId,
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => cmdbApi.createRelationship(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ci-relationships', itemId] })
      setShowCreateForm(false)
      setNewRelType('depends_on')
      setNewTargetId('')
      setNewProperties('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (relId: number) => cmdbApi.deleteRelationship(relId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ci-relationships', itemId] })
    },
  })

  if (!itemId) return <div className="error">No CI item ID provided</div>

  return (
    <div style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ margin: 0 }}>Relationships</h2>
          <p style={{ color: '#666', margin: '0.25rem 0 0' }}>
            <Link to={`/cmdb/items/${itemId}`}>← Back to CI Item</Link>
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? 'Cancel' : '+ Add Relationship'}
        </button>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <h3 className="card-title">New Relationship</h3>
          </div>
          <div style={{ padding: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Relationship Type</label>
              <select
                className="form-input"
                value={newRelType}
                onChange={(e) => setNewRelType(e.target.value)}
              >
                {RELATIONSHIP_TYPES.map(type => (
                  <option key={type} value={type}>{type.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Target CI Item ID</label>
              <input
                type="number"
                className="form-input"
                value={newTargetId}
                onChange={(e) => setNewTargetId(e.target.value)}
                placeholder="e.g. 42"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Properties (JSON, optional)</label>
              <textarea
                className="form-textarea"
                value={newProperties}
                onChange={(e) => setNewProperties(e.target.value)}
                placeholder='{"weight": "heavy", "note": "production server"}'
                rows={3}
              />
            </div>

            <button
              className="btn btn-primary"
              onClick={() => {
                if (!newTargetId) return
                createMutation.mutate({
                  source_ci_id: itemId,
                  target_ci_id: parseInt(newTargetId),
                  relationship_type: newRelType,
                  properties: newProperties ? JSON.parse(newProperties) : {}
                })
              }}
              disabled={createMutation.isPending || !newTargetId}
            >
              {createMutation.isPending ? 'Creating...' : 'Create Relationship'}
            </button>
          </div>
        </div>
      )}

      {/* Relationships list */}
      {isLoading ? (
        <div className="loading">Loading relationships...</div>
      ) : relationships && relationships.length > 0 ? (
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          {relationships.map(rel => (
            <div key={rel.id} className="card" style={{ borderLeft: `4px solid ${rel.is_active ? '#28a745' : '#dc3545'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                    {rel.source_type_name || `CI #${rel.source_ci_id}`}
                    <span style={{ color: '#666', margin: '0 0.5rem' }}>&#8594; {rel.relationship_type.replace(/_/g, ' ')} &#8594;</span>
                    <Link to={`/cmdb/items/${rel.target_ci_id}`} style={{ color: '#007bff' }}>
                      {rel.target_type_name || `CI #${rel.target_ci_id}`}
                    </Link>
                  </div>
                  {rel.properties && Object.keys(rel.properties).length > 0 && (
                    <div style={{ fontSize: '0.85rem', color: '#666' }}>
                      Properties: {JSON.stringify(rel.properties)}
                    </div>
                  )}
                </div>
                <button
                  className="btn btn-sm btn-danger"
                  onClick={() => {
                    if (confirm('Delete this relationship?')) {
                      deleteMutation.mutate(rel.id)
                    }
                  }}
                  disabled={deleteMutation.isPending}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '2rem', color: '#666' }}>
          No relationships for this CI item yet.
        </div>
      )}
    </div>
  )
}
