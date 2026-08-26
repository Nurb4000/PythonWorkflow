/**
 * Graphical Data Maintenance Console — Edit data directly with validation.
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = '/api'

interface DataTableRow {
  id: number
  [key: string]: any
}

interface DataTable {
  name: string
  columns: Array<{name: string; type: string}>
  rows: DataTableRow[]
}

export const DataMaintenanceConsole: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedTable, setSelectedTable] = useState('')
  const [editingRow, setEditingRow] = useState<DataTableRow | null>(null)
  const [editForm, setEditForm] = useState<Record<string, any>>({})

  const { data: tables } = useQuery({
    queryKey: ['maintenance-tables'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/admin/data-maintenance/tables`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data as DataTable[]
    }
  })

  const updateMutation = useMutation({
    mutationFn: async ({ table, id, data }: { table: string; id: number; data: Record<string, any> }) => {
      const token = localStorage.getItem('token')
      return await axios.put(`${API_URL}/admin/data-maintenance/${table}/${id}`, data, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-tables'] })
      setEditingRow(null)
      setEditForm({})
    }
  })

  const handleEdit = (row: DataTableRow) => {
    setEditingRow(row)
    setEditForm({...row})
  }

  const handleSave = () => {
    if (!editingRow || !selectedTable) return
    updateMutation.mutate({ table: selectedTable, id: editingRow.id, data: editForm })
  }

  return (
    <div style={{ padding: '1.5rem' }}>
      <h2 style={{ marginBottom: '1.5rem' }}>Data Maintenance Console</h2>
      
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: '2rem' }}>
        {/* Table Selector */}
        <div>
          <h3 style={{ marginBottom: '1rem' }}>Tables</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {tables?.map(table => (
              <button
                key={table.name}
                className={`btn ${selectedTable === table.name ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setSelectedTable(table.name)}
                style={{ textAlign: 'left' }}
              >
                {table.name}
              </button>
            ))}
          </div>
        </div>

        {/* Data Grid */}
        <div>
          {selectedTable && tables?.find(t => t.name === selectedTable) && (
            <>
              <h3 style={{ marginBottom: '1rem' }}>{selectedTable}</h3>
              
              {/* Edit Form */}
              {editingRow && (
                <div className="card" style={{ marginBottom: '1rem', backgroundColor: '#f8f9fa' }}>
                  <div className="card-header">
                    <h4 className="card-title">Edit Row #{editingRow.id}</h4>
                  </div>
                  <div style={{ padding: '1rem' }}>
                    {tables.find(t => t.name === selectedTable)!.columns.map(col => (
                      <div key={col.name} className="form-group">
                        <label className="form-label">{col.name}</label>
                        <input
                          type={col.type === 'number' ? 'number' : 'text'}
                          className="form-input"
                          value={editForm[col.name] || ''}
                          onChange={(e) => setEditForm({...editForm, [col.name]: col.type === 'number' ? parseInt(e.target.value) : e.target.value})}
                        />
                      </div>
                    ))}
                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                      <button className="btn btn-success" onClick={handleSave} disabled={updateMutation.isPending}>
                        {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                      </button>
                      <button className="btn btn-secondary" onClick={() => setEditingRow(null)}>Cancel</button>
                    </div>
                  </div>
                </div>
              )}

              {/* Data Table */}
              <table className="table">
                <thead>
                  <tr>
                    {tables.find(t => t.name === selectedTable)!.columns.map(col => (
                      <th key={col.name}>{col.name}</th>
                    ))}
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tables.find(t => t.name === selectedTable)!.rows.map(row => (
                    <tr key={row.id}>
                      {tables.find(t => t.name === selectedTable)!.columns.map(col => (
                        <td key={col.name}>{row[col.name]}</td>
                      ))}
                      <td>
                        <button className="btn btn-sm btn-primary" onClick={() => handleEdit(row)}>Edit</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
