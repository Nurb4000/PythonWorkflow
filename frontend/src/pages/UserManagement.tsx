import React, { useState } from 'react'
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
}

export const UserManagement: React.FC = () => {
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', role: 'user', full_name: '' })
  const [newUserCustomData, setNewUserCustomData] = useState<Record<string, any>>({})
  const [newGroup, setNewGroup] = useState({ name: '', description: '', group_type: 'internal' })
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editForm, setEditForm] = useState({ full_name: '', email: '', role: '', password: '', is_active: true })
  const [editCustomData, setEditCustomData] = useState<Record<string, any>>({})
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [editGroupForm, setEditGroupForm] = useState({ name: '', description: '', group_type: 'internal', is_active: true })
  const [error, setError] = useState('')
  const [showUserModal, setShowUserModal] = useState(false)
  const [showGroupModal, setShowGroupModal] = useState(false)
  const queryClient = useQueryClient()

  const { data: users, isLoading: usersLoading, isError: usersError, error: usersErrorObj } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await authApi.listUsers()
      return response.data as User[]
    }
  })

  const { data: groups, isLoading: groupsLoading } = useQuery({
    queryKey: ['groups'],
    queryFn: async () => {
      const response = await authApi.listGroups()
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
      setError(err.response?.data?.detail || 'Failed to delete user')
    }
  })

  const updateGroupMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      authApi.updateGroup(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'], refetchType: 'all' })
      queryClient.invalidateQueries({ queryKey: ['users'], refetchType: 'all' })
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
      setError(err.response?.data?.detail || 'Failed to delete group')
    }
  })

  if (usersLoading || groupsLoading) {
    return <div className="loading">Loading users and groups...</div>
  }

  if (usersError) {
    console.error('Users query error:', usersErrorObj)
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

  const openEditGroup = (group: Group) => {
    setEditingGroup(group)
    setEditGroupForm({ name: group.name, description: group.description, group_type: group.group_type, is_active: group.is_active })
    setShowGroupModal(true)
  }

  const closeEditGroup = () => {
    setShowGroupModal(false)
    setEditingGroup(null)
  }

  return (
    <div>
      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      <div className="card-header">
        <h2>User & Group Management</h2>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn btn-primary" onClick={() => setShowCreateUser(!showCreateUser)}>
            {showCreateUser ? 'Cancel' : '+ New User'}
          </button>
          <button className="btn btn-success" onClick={() => setShowCreateGroup(!showCreateGroup)}>
            {showCreateGroup ? 'Cancel' : '+ New Group'}
          </button>
        </div>
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

      {/* Users Table */}
      <div className="card">
        <h3 className="card-title">Users ({users?.length || 0})</h3>
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
            {users?.map((user: User) => (
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
                    className="btn btn-sm btn-danger"
                    onClick={() => deleteUserMutation.mutate(user.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Groups Table */}
      <div className="card">
        <h3 className="card-title">Groups ({groups?.length || 0})</h3>
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
            {groups?.map((group: Group) => (
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
                    className="btn btn-sm btn-danger"
                    onClick={() => deleteGroupMutation.mutate(group.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
              updateGroupMutation.mutate({ id: editingGroup.id, data: editGroupForm })
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
