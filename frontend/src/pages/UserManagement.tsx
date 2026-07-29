import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = '/api'

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
}

interface Group {
  id: number
  name: string
  description: string
  group_type: string
  user_count: number
  users: Array<{id: number, username: string}>
}

export const UserManagement: React.FC = () => {
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', role: 'user', full_name: '' })
  const [newGroup, setNewGroup] = useState({ name: '', description: '', group_type: 'internal' })
  const queryClient = useQueryClient()

  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/auth/users`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data as User[]
    }
  })

  const { data: groups, isLoading: groupsLoading } = useQuery({
    queryKey: ['groups'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/auth/groups`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data as Group[]
    }
  })

  const createUserMutation = useMutation({
    mutationFn: async (data: any) => {
      const token = localStorage.getItem('token')
      const response = await axios.post(`${API_URL}/auth/register`, null, {
        params: data,
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateUser(false)
      setNewUser({ username: '', email: '', password: '', role: 'user', full_name: '' })
    }
  })

  const createGroupMutation = useMutation({
    mutationFn: async (data: any) => {
      const token = localStorage.getItem('token')
      const response = await axios.post(`${API_URL}/auth/groups`, null, {
        params: data,
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'] })
      setShowCreateGroup(false)
      setNewGroup({ name: '', description: '', group_type: 'internal' })
    }
  })

  const updateUserMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: any }) => {
      const token = localStorage.getItem('token')
      const response = await axios.put(`${API_URL}/auth/users/${id}`, null, {
        params: data,
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    }
  })

  const deleteUserMutation = useMutation({
    mutationFn: async (id: number) => {
      const token = localStorage.getItem('token')
      await axios.delete(`${API_URL}/auth/users/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    }
  })

  if (usersLoading || groupsLoading) {
    return <div className="loading">Loading users and groups...</div>
  }

  return (
    <div>
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
            createUserMutation.mutate(newUser)
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
                <td>
                  <select 
                    className="form-select" 
                    style={{ width: 'auto' }}
                    value={user.role}
                    onChange={(e) => updateUserMutation.mutate({ id: user.id, data: { role: e.target.value } })}
                  >
                    <option value="user">User</option>
                    <option value="staff">Staff</option>
                    <option value="developer">Developer</option>
                    <option value="admin">Admin</option>
                  </select>
                </td>
                <td>
                  {user.groups.map(g => (
                    <span key={g.id} className="badge badge-info" style={{ marginRight: '0.25rem' }}>{g.name}</span>
                  ))}
                </td>
                <td>
                  <span className={`badge ${user.is_active ? 'badge-success' : 'badge-danger'}`}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>{user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}</td>
                <td>
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

      <div className="card">
        <h3 className="card-title">Groups ({groups?.length || 0})</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Type</th>
              <th>Users</th>
            </tr>
          </thead>
          <tbody>
            {groups?.map((group: Group) => (
              <tr key={group.id}>
                <td><strong>{group.name}</strong></td>
                <td>{group.description}</td>
                <td>{group.group_type}</td>
                <td>{group.user_count} users</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
