/**
 * CI Dependency Graph Page — visualizes relationships for a specific CI item.
 */
import React from 'react'
import { useParams, Link } from 'react-router-dom'
import CIDependencyGraph from '../components/CIDependencyGraph'

export const CIDependencyGraphPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const itemId = parseInt(id!)

  if (!itemId) {
    return <div className="error">Invalid CI item ID</div>
  }

  return (
    <div style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>CI Dependency Graph</h2>
        <Link to={`/cmdb/items/${itemId}`} className="btn btn-secondary">← Back to CI Item</Link>
      </div>
      
      <div style={{ marginBottom: '1rem', color: '#666' }}>
        Visualizing dependencies up to depth 2. Use the graph to understand impact of changes.
      </div>

      <CIDependencyGraph itemId={itemId} depth={2} />
    </div>
  )
}
