import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../services/api'
import { CustomFieldsEditor } from '../components/CustomFieldsEditor'

interface User {
  id: number
  username: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  mfa_enabled: boolean
  groups: Array<{id: number, name: string}>
  created_at: string
  last_login: string
  custom_data?: Record<string, any>
}

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

export const UsersPage: React.FC = () => {
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', role: 'user', full_name: '' })
  const [newUserCustomData, setNewUserCustomData] = useState<Record<string, any>>({})
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editForm, setEditForm] = useState({ full_name: '', email: '', role: '', password: '', is_active: true })
  const [editCustomData, setEditCustomData] = useState<Record<string, any>>({})
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [error, setError] = useState('')
  const [showUserModal, setShowUserModal] = useState(false)

  // Filter state
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [roleFilter, setRoleFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [groupFilter, setGroupFilter] = useState<string>('')
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setSearchTerm(searchInput), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchInput])

  const queryClient = useQueryClient()

  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ['users', statusFilter],
    queryFn: async () => {
      const includeInactive = !statusFilter || statusFilter === 'inactive'
      const response = await authApi.listUsers(includeInactive)
      return response.data as User[]
    }
  })

  const { data: groups } = useQuery({
    queryKey: ['groups', false],
    queryFn: async () => {
      const response = await authApi.listGroups(false)
      return response.data as Group[]
    }
  })

  const createUserMutation = useMutation({
    mutationFn: (data: any) => authApi.createUser ? authApi.createUser(data) : Promise.reject('no-op'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'], refetchType: 'all' })
      setShowCreateUser(false)
      setNewUser({ username: '', email: '', password: '', role: 'user', full_name: '' })
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create user')
    }
  })

  const updateUserMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      authApi.updateUser(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'], refetchType: 'all' })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update user')
    }
  })

  const setUserGroupsMutation = useMutation({
    mutationFn: ({ id, groupIds }: { id: number; groupIds: number[] }) =>
      authApi.setUserGroups(id, groupIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'], refetchType: 'all' })
      queryClient.invalidateQueries({ queryKey: ['groups'], refetchType: 'all' })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update group membership')
    }
  })

  const deleteUserMutation = useMutation({
    mutationFn: (id: number) => authApi.deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'], refetchType: 'all' })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to deactivate user')
    }
  })

  if (usersLoading) {
    return <div className="loading">Loading users...</div>
  }

  const toggleGroup = (groupId: number) => {
    setSelectedGroupIds(prev =>
      prev.includes(groupId) ? prev.filter(id => id !== groupId) : [...prev, groupId]
    )
  }

  const openEditUser = (user: User) => {
    setEditingUser(user)
    setEditForm({ full_name: user.full_name, email: user.email, role: user.role, password: '', is_active: user.is_active })
    setSelectedGroupIds(user.groups.map((g: any) => g.id))
    setEditCustomData(user.custom_data || {})
    setShowUserModal(true)
  }

  const closeEditUser = () => {
    setShowUserModal(false)
    setEditingUser(null)
  }

  const filteredUsers = (users || []).filter((user: User) => {
    if (statusFilter === 'active' && !user.is_active) return false
    if (statusFilter === 'inactive' && user.is_active) return false
    if (roleFilter && user.role !== roleFilter) return false
    if (groupFilter && !user.groups.some((g: any) => g.id === parseInt(groupFilter))) return false
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      return (
        user.username.toLowerCase().includes(q) ||
        user.email.toLowerCase().includes(q) ||
        (user.full_name || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div>
      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      <div className="card-header">
        <h2>Users</h2>
        <button className="btn btn-primary" onClick={() => setShowCreateUser(!showCreateUser)}>
          {showCreateUser ? 'Cancel' : '+ New User'}
        </button>
      </div>

      {showCreateUser && (
        <div className="card">
          <h3 className="card-title">Create User</h3>
          <form onSubmit={(e) => {
            e.preventDefault()
            createUserMutation.mutate({ ...newUser, custom_data: newUserCustomData })
          }}>
            <div className="grid grid-2">
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <input type="text" className="form-input" value={newUser.full_name} onChange={(e) => setNewUser({...newUser, full_name: e.target.value})} />
              </div>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input type="text" className="form-input" value={newUser.username} onChange={(e) => setNewUser({...newUser, username: e.target.value})} required />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input type="email" className="form-input" value={newUser.email} onChange={(e) => setNewUser({...newUser, email: e.target.value})} required />
              </div>
              <div className="form-group">
                <label className="form-label">Password</label>
                <input type="password" className="form-input" value={newUser.password} onChange={(e) => setNewUser({...newUser, password: e.target.value})} required />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Role</label>
              <select className="form-select" value={newUser.role} onChange={(e) => setNewUser({...newUser, role: e.target.value})}>
                <option value="user">User</option>
                <option value="staff">Staff</option>
                <option value="developer">Developer</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <CustomFieldsEditor
              targetTable="users"
              existingData={newUserCustomData}
              onChange={setNewUserCustomData}
            />
            <button type="submit" className="btn btn-success" disabled={createUserMutation.isPending}>
              {createUserMutation.isPending ? 'Creating...' : 'Create User'}
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
              placeholder="Search by name, email, or username..."
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
            <label className="form-label">Role</label>
            <select
              className="form-select"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            >
              <option value="">All Roles</option>
              <option value="user">User</option>
              <option value="staff">Staff</option>
              <option value="developer">Developer</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0, minWidth: '150px' }}>
            <label className="form-label">Group</label>
            <select
              className="form-select"
              value={groupFilter}
              onChange={(e) => setGroupFilter(e.target.value)}
            >
              <option value="">All Groups</option>
              {(groups || []).map((g: Group) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          {(searchInput || statusFilter !== 'active' || roleFilter || groupFilter) && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => { setSearchInput(''); setSearchTerm(''); setStatusFilter('active'); setRoleFilter(''); setGroupFilter('') }}
              style={{ marginBottom: 0 }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Users Table */}
      <div className="card">
        <h3 className="card-title" style={{ margin: 0 }}>Users ({filteredUsers.length})</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Username</th>
              <th>Email</th>
              <th>Role</th>
              <th>Groups</th>
              <th>Status</th>
              <th>Last Login</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user: User) => (
              <tr key={user.id}>
                <td>{user.full_name}</td>
                <td>{user.username}</td>
                <td>{user.email}</td>
                <td>{user.role}</td>
                <td>
                  {user.groups.map((g: any) => (
                    <span key={g.id} className="badge badge-info" style={{ marginRight: '0.25rem' }}>{g.name}</span>
                  ))}
                </td>
                <td>
                  <span className={`badge ${user.is_active ? 'badge-success' : 'badge-danger'}`}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>{user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button 
                    className="btn btn-sm btn-primary" 
                    style={{ marginRight: '0.3rem' }}
                    onClick={() => openEditUser(user)}
                  >
                    Edit
                  </button>
                  <button 
                    className="btn btn-sm btn-warning"
                    onClick={() => deleteUserMutation.mutate(user.id)}
                  >
                    Deactivate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredUsers.length === 0 && (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#7f8c8d' }}>
            No users match your filters.
          </div>
        )}
      </div>

      {/* Edit User Modal */}
      {showUserModal && editingUser && (
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
            maxWidth: '600px',
            width: '90%',
            maxHeight: '90vh',
            overflow: 'auto'
          }}>
            <h3 style={{ marginTop: 0 }}>Edit User: {editingUser.username}</h3>
            <form onSubmit={(e) => {
              e.preventDefault()
              const data: any = { full_name: editForm.full_name, email: editForm.email, role: editForm.role, is_active: editForm.is_active, custom_data: editCustomData }
              if (editForm.password) data.password = editForm.password
              updateUserMutation.mutate({ id: editingUser.id, data })
              setUserGroupsMutation.mutate({ id: editingUser.id, groupIds: selectedGroupIds })
              closeEditUser()
            }}>
              <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Full Name</label>
                  <input type="text" className="form-input" value={editForm.full_name} onChange={(e) => setEditForm({...editForm, full_name: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Email</label>
                  <input type="email" className="form-input" value={editForm.email} onChange={(e) => setEditForm({...editForm, email: e.target.value})} required />
                </div>
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">New Password (leave blank to keep current)</label>
                <input type="password" className="form-input" value={editForm.password} onChange={(e) => setEditForm({...editForm, password: e.target.value})} />
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Role</label>
                <select className="form-select" value={editForm.role} onChange={(e) => setEditForm({...editForm, role: e.target.value})}>
                  <option value="user">User</option>
                  <option value="staff">Staff</option>
                  <option value="developer">Developer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={editForm.is_active} onChange={(e) => setEditForm({...editForm, is_active: e.target.checked})} />
                  Account Active
                </label>
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label">Groups</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {(groups || []).map((g: any) => (
                    <label key={g.id} style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      padding: '0.25rem 0.5rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.85rem'
                    }}>
                      <input
                        type="checkbox"
                        checked={selectedGroupIds.includes(g.id)}
                        onChange={() => toggleGroup(g.id)}
                      />
                      {g.name}
                    </label>
                  ))}
                  {(!groups || groups.length === 0) && (
                    <small style={{ color: '#7f8c8d' }}>No groups available</small>
                  )}
                </div>
              </div>
              <CustomFieldsEditor
                targetTable="users"
                existingData={editCustomData}
                onChange={setEditCustomData}
              />
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button type="submit" className="btn btn-primary" disabled={updateUserMutation.isPending || setUserGroupsMutation.isPending}>
                  {updateUserMutation.isPending || setUserGroupsMutation.isPending ? 'Saving...' : 'Save'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={closeEditUser}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
