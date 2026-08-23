import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../services/api'

interface Group {
  id: number
  name: string
  description: string
  group_type: string
  is_active: boolean
  user_count: number
  users: Array<{id: number, username: string}>
  custom_data?: Record<string, any>
}

export const GroupsPage: React.FC = () => {
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [newGroup, setNewGroup] = useState({ name: '', description: '', group_type: 'internal' })
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [editGroupForm, setEditGroupForm] = useState({ name: '', description: '', group_type: 'internal', is_active: true })
  const [error, setError] = useState('')
  const [showGroupModal, setShowGroupModal] = useState(false)

  // OLA editor state (Task-level SLA)
  const [olaEnabled, setOlaEnabled] = useState(false)
  const [olaPickupDefault, setOlaPickupDefault] = useState('')
  const [olaClosureDefault, setOlaClosureDefault] = useState('')
  const [olaPickupHours, setOlaPickupHours] = useState({ '1': '', '2': '', '3': '', '4': '' })
  const [olaClosureHours, setOlaClosureHours] = useState({ '1': '', '2': '', '3': '', '4': '' })

  // Filter state
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setSearchTerm(searchInput), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchInput])

  const queryClient = useQueryClient()

  const { data: groups, isLoading: groupsLoading } = useQuery({
    queryKey: ['groups', statusFilter],
    queryFn: async () => {
      const includeInactive = !statusFilter || statusFilter === 'inactive'
      const response = await authApi.listGroups(includeInactive)
      return response.data as Group[]
    }
  })

  const createGroupMutation = useMutation({
    mutationFn: (data: any) => authApi.createGroup(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'], refetchType: 'all' })
      setShowCreateGroup(false)
      setNewGroup({ name: '', description: '', group_type: 'internal' })
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create group')
    }
  })

  const updateGroupMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      authApi.updateGroup(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'], refetchType: 'all' })
      setEditingGroup(null)
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update group')
    }
  })

  const deleteGroupMutation = useMutation({
    mutationFn: (id: number) => authApi.deleteGroup(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'], refetchType: 'all' })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to deactivate group')
    }
  })

  if (groupsLoading) {
    return <div className="loading">Loading groups...</div>
  }

  const openEditGroup = (group: Group) => {
    setEditingGroup(group)
    setEditGroupForm({ name: group.name, description: group.description, group_type: group.group_type, is_active: group.is_active })

    // Load OLA targets from group custom_data
    const ola = (group.custom_data || {}).ola_targets
    if (ola) {
      setOlaEnabled(true)
      setOlaPickupDefault(ola.pickup_hours?.default ?? '')
      setOlaClosureDefault(ola.closure_hours?.default ?? '')
      setOlaPickupHours({
        '1': ola.pickup_hours?.['1'] ?? '',
        '2': ola.pickup_hours?.['2'] ?? '',
        '3': ola.pickup_hours?.['3'] ?? '',
        '4': ola.pickup_hours?.['4'] ?? '',
      })
      setOlaClosureHours({
        '1': ola.closure_hours?.['1'] ?? '',
        '2': ola.closure_hours?.['2'] ?? '',
        '3': ola.closure_hours?.['3'] ?? '',
        '4': ola.closure_hours?.['4'] ?? '',
      })
    } else {
      setOlaEnabled(false)
      setOlaPickupDefault('')
      setOlaClosureDefault('')
      setOlaPickupHours({ '1': '', '2': '', '3': '', '4': '' })
      setOlaClosureHours({ '1': '', '2': '', '3': '', '4': '' })
    }
    setShowGroupModal(true)
  }

  const closeEditGroup = () => {
    setShowGroupModal(false)
    setEditingGroup(null)
    setOlaEnabled(false)
    setOlaPickupDefault('')
    setOlaClosureDefault('')
    setOlaPickupHours({ '1': '', '2': '', '3': '', '4': '' })
    setOlaClosureHours({ '1': '', '2': '', '3': '', '4': '' })
  }

  const filteredGroups = (groups || []).filter((group: Group) => {
    if (statusFilter === 'active' && !group.is_active) return false
    if (statusFilter === 'inactive' && group.is_active) return false
    if (typeFilter && group.group_type !== typeFilter) return false
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      return (
        group.name.toLowerCase().includes(q) ||
        (group.description || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div>
      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      <div className="card-header">
        <h2>Groups</h2>
        <button className="btn btn-success" onClick={() => setShowCreateGroup(!showCreateGroup)}>
          {showCreateGroup ? 'Cancel' : '+ New Group'}
        </button>
      </div>

      {showCreateGroup && (
        <div className="card">
          <h3 className="card-title">Create Group</h3>
          <form onSubmit={(e) => {
            e.preventDefault()
            createGroupMutation.mutate(newGroup)
          }}>
            <div className="form-group">
              <label className="form-label">Group Name</label>
              <input type="text" className="form-input" value={newGroup.name} onChange={(e) => setNewGroup({...newGroup, name: e.target.value})} required />
            </div>
            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea className="form-textarea" value={newGroup.description} onChange={(e) => setNewGroup({...newGroup, description: e.target.value})} />
            </div>
            <button type="submit" className="btn btn-success" disabled={createGroupMutation.isPending}>
              {createGroupMutation.isPending ? 'Creating...' : 'Create Group'}
            </button>
          </form>
        </div>
      )}

      {/* Search and Filter controls */}
      <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Search</label>
            <input
              type="text"
              className="form-input"
              placeholder="Search by name or description..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0, minWidth: '130px' }}>
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="">All</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0, minWidth: '130px' }}>
            <label className="form-label">Type</label>
            <select
              className="form-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">All Types</option>
              <option value="internal">Internal</option>
              <option value="ldap">LDAP</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          {(searchInput || statusFilter !== 'active' || typeFilter) && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => { setSearchInput(''); setSearchTerm(''); setStatusFilter('active'); setTypeFilter('') }}
              style={{ marginBottom: 0 }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Groups Table */}
      <div className="card">
        <h3 className="card-title" style={{ margin: 0 }}>Groups ({filteredGroups.length})</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Type</th>
              <th>Users</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredGroups.map((group: Group) => (
              <tr key={group.id}>
                <td><strong>{group.name}</strong></td>
                <td>{group.description}</td>
                <td>{group.group_type}</td>
                <td>{group.user_count} users</td>
                <td>
                  <span className={`badge ${group.is_active ? 'badge-success' : 'badge-danger'}`}>
                    {group.is_active ? 'Active' : 'Disabled'}
                  </span>
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button
                    className="btn btn-sm btn-primary"
                    style={{ marginRight: '0.3rem' }}
                    onClick={() => openEditGroup(group)}
                  >
                    Edit
                  </button>
                  <button
                    className="btn btn-sm btn-warning"
                    onClick={() => deleteGroupMutation.mutate(group.id)}
                  >
                    Deactivate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredGroups.length === 0 && (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#7f8c8d' }}>
            No groups match your filters.
          </div>
        )}
      </div>

      {/* Edit Group Modal */}
      {showGroupModal && editingGroup && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'white',
            borderRadius: '8px',
            padding: '2rem',
            maxWidth: '500px',
            width: '90%'
          }}>
            <h3 style={{ marginTop: 0 }}>Edit Group: {editingGroup.name}</h3>
            <form onSubmit={(e) => {
              e.preventDefault()
              // Build custom_data with OLA targets
              const customData: any = {}
              if (olaEnabled) {
                customData.ola_targets = {
                  pickup_hours: {
                    default: olaPickupDefault ? parseInt(olaPickupDefault) : null,
                    '1': olaPickupHours['1'] ? parseInt(olaPickupHours['1']) : undefined,
                    '2': olaPickupHours['2'] ? parseInt(olaPickupHours['2']) : undefined,
                    '3': olaPickupHours['3'] ? parseInt(olaPickupHours['3']) : undefined,
                    '4': olaPickupHours['4'] ? parseInt(olaPickupHours['4']) : undefined,
                  },
                  closure_hours: {
                    default: olaClosureDefault ? parseInt(olaClosureDefault) : null,
                    '1': olaClosureHours['1'] ? parseInt(olaClosureHours['1']) : undefined,
                    '2': olaClosureHours['2'] ? parseInt(olaClosureHours['2']) : undefined,
                    '3': olaClosureHours['3'] ? parseInt(olaClosureHours['3']) : undefined,
                    '4': olaClosureHours['4'] ? parseInt(olaClosureHours['4']) : undefined,
                  },
                }
              }
              updateGroupMutation.mutate({ id: editingGroup.id, data: { ...editGroupForm, custom_data: customData } })
              closeEditGroup()
            }}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Group Name</label>
                <input type="text" className="form-input" value={editGroupForm.name} onChange={(e) => setEditGroupForm({...editGroupForm, name: e.target.value})} required />
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Description</label>
                <textarea className="form-textarea" value={editGroupForm.description} onChange={(e) => setEditGroupForm({...editGroupForm, description: e.target.value})} rows={3} />
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Type</label>
                <select className="form-select" value={editGroupForm.group_type} onChange={(e) => setEditGroupForm({...editGroupForm, group_type: e.target.value})}>
                  <option value="internal">internal</option>
                  <option value="ldap">ldap</option>
                  <option value="custom">custom</option>
                </select>
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={editGroupForm.is_active} onChange={(e) => setEditGroupForm({...editGroupForm, is_active: e.target.checked})} />
                  Group Active (disable to hide from users)
                </label>
              </div>

              {/* OLA Targets Editor */}
              <div style={{ padding: '1rem', border: '1px solid #dee2e6', borderRadius: '6px', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                  <h4 style={{ margin: 0, fontSize: '1rem' }}>OLA Targets (Internal)</h4>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={olaEnabled}
                      onChange={e => setOlaEnabled(e.target.checked)}
                    />
                    Enable OLA tracking
                  </label>
                </div>
                {olaEnabled && (
                  <div>
                    <p style={{ fontSize: '0.85rem', color: '#6c757d', margin: '0 0 0.75rem' }}>
                      Set default pickup and closure time targets (in hours). Optionally override per priority below. Applied to human tasks assigned to this group.
                    </p>
                    <table className="table" style={{ marginBottom: '0.75rem' }}>
                      <thead>
                        <tr>
                          <th>Target</th>
                          <th>Default (hours)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>Pickup</td>
                          <td>
                            <input
                              type="number"
                              className="form-input"
                              style={{ width: '100px' }}
                              value={olaPickupDefault}
                              onChange={e => setOlaPickupDefault(e.target.value)}
                              placeholder="—"
                              min="0"
                            />
                          </td>
                        </tr>
                        <tr>
                          <td>Closure</td>
                          <td>
                            <input
                              type="number"
                              className="form-input"
                              style={{ width: '100px' }}
                              value={olaClosureDefault}
                              onChange={e => setOlaClosureDefault(e.target.value)}
                              placeholder="—"
                              min="0"
                            />
                          </td>
                        </tr>
                      </tbody>
                    </table>
                    <details>
                      <summary style={{ cursor: 'pointer', fontSize: '0.85rem', color: '#6c757d' }}>Per-priority overrides (optional)</summary>
                      <table className="table" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Priority</th>
                            <th>Pickup (hours)</th>
                            <th>Closure (hours)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {([
                            { id: '1', name: 'Critical', color: '#dc3545' },
                            { id: '2', name: 'High', color: '#fd7e14' },
                            { id: '3', name: 'Medium', color: '#ffc107' },
                            { id: '4', name: 'Low', color: '#28a745' },
                          ] as const).map((lvl) => (
                            <tr key={lvl.id}>
                              <td>
                                <span style={{
                                  display: 'inline-block', width: '10px', height: '10px',
                                  borderRadius: '50%', backgroundColor: lvl.color, marginRight: '6px'
                                }} />
                                {lvl.name}
                              </td>
                              <td>
                                <input
                                  type="number"
                                  className="form-input"
                                  style={{ width: '100px' }}
                                  value={olaPickupHours[lvl.id]}
                                  onChange={e => setOlaPickupHours({ ...olaPickupHours, [lvl.id]: e.target.value })}
                                  placeholder="use default"
                                  min="0"
                                />
                              </td>
                              <td>
                                <input
                                  type="number"
                                  className="form-input"
                                  style={{ width: '100px' }}
                                  value={olaClosureHours[lvl.id]}
                                  onChange={e => setOlaClosureHours({ ...olaClosureHours, [lvl.id]: e.target.value })}
                                  placeholder="use default"
                                  min="0"
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </details>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button type="submit" className="btn btn-primary" disabled={updateGroupMutation.isPending}>
                  {updateGroupMutation.isPending ? 'Saving...' : 'Save'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={closeEditGroup}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
