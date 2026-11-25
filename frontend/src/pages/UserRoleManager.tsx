/**
 * User Role Manager — Assign roles to users via admin interface.
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = '/api'

interface User {
  id: number
  username: string
  email: string
  full_name: string
  roles: string[]
  is_active: boolean
}

interface Role {
  id: number
  name: string
  description: string
}

export const UserRoleManager: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedRoles, setSelectedRoles] = useState<string[]>([])
  const [message, setMessage] = useState('')

  const { data: usersData } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/auth/users`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data as User[]
    }
  })

  const { data: rolesData } = useQuery({
    queryKey: ['roles'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/admin/roles/`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data.items as Role[]
    }
  })

  const updateRolesMutation = useMutation({
    mutationFn: async ({ userId, roles }: { userId: number; roles: string[] }) => {
      const token = localStorage.getItem('token')
      return await axios.put(
        `${API_URL}/auth/users/${userId}`,
        null,
        {
          params: { roles: JSON.stringify(roles) },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setMessage('Roles updated successfully')
      setTimeout(() => setMessage(''), 3000)
    },
    onError: (err: any) => {
      setMessage(err.response?.data?.detail || 'Failed to update roles')
      setTimeout(() => setMessage(''), 5000)
    }
  })

  const handleRoleToggle = (role: string) => {
    if (selectedRoles.includes(role)) {
      setSelectedRoles(selectedRoles.filter(r => r !== role))
    } else {
      setSelectedRoles([...selectedRoles, role])
    }
  }

  const handleSave = () => {
    if (!selectedUserId || selectedRoles.length === 0) return
    updateRolesMutation.mutate({ userId: selectedUserId, roles: selectedRoles })
  }

  const allRoles = ['admin', 'developer', 'staff', 'user', 'cmdb_manager']

  return (
    <div style={{ padding: '1.5rem' }}>
      <h2 style={{ marginBottom: '1.5rem' }}>User Role Management</h2>

      {message && (
        <div style={{
          padding: '0.75rem',
          borderRadius: '4px',
          marginBottom: '1rem',
          backgroundColor: message.includes('Failed') ? '#f8d7da' : '#d4edda',
          color: message.includes('Failed') ? '#721c24' : '#155724'
        }}>
          {message}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
        {/* User List */}
        <div>
          <h3 style={{ marginBottom: '1rem' }}>Users</h3>
          <div style={{ maxHeight: '500px', overflow: 'auto' }}>
            {usersData?.map(user => (
              <div
                key={user.id}
                style={{
                  padding: '0.75rem',
                  marginBottom: '0.5rem',
                  backgroundColor: selectedUserId === user.id ? '#e3f2fd' : '#fff',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
                onClick={() => {
                  setSelectedUserId(user.id)
                  setSelectedRoles(user.roles || [])
                }}
              >
                <div style={{ fontWeight: 600 }}>{user.full_name || user.username}</div>
                <div style={{ fontSize: '0.85rem', color: '#666' }}>{user.email}</div>
                <div style={{ fontSize: '0.75rem', color: '#999' }}>
                  Roles: {(user.roles || []).join(', ') || 'None'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Role Assignment */}
        <div>
          <h3 style={{ marginBottom: '1rem' }}>
            {selectedUserId ? `Assign Roles to User #${selectedUserId}` : 'Select a user'}
          </h3>

          {selectedUserId && (
            <>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 600 }}>
                  Available Roles:
                </label>
                {allRoles.map(role => (
                  <label key={role} style={{ display: 'block', marginBottom: '0.25rem' }}>
                    <input
                      type="checkbox"
                      checked={selectedRoles.includes(role)}
                      onChange={() => handleRoleToggle(role)}
                      style={{ marginRight: '0.5rem' }}
                    />
                    {role}
                  </label>
                ))}
              </div>

              {rolesData && rolesData.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 600 }}>
                    Custom Roles:
                  </label>
                  {rolesData.map(role => (
                    <label key={role.id} style={{ display: 'block', marginBottom: '0.25rem' }}>
                      <input
                        type="checkbox"
                        checked={selectedRoles.includes(role.name)}
                        onChange={() => handleRoleToggle(role.name)}
                        style={{ marginRight: '0.5rem' }}
                      />
                      {role.name} {role.description && <small>({role.description})</small>}
                    </label>
                  ))}
                </div>
              )}

              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={updateRolesMutation.isPending || selectedRoles.length === 0}
              >
                {updateRolesMutation.isPending ? 'Saving...' : 'Save Roles'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
