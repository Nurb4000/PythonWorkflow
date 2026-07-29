import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { WorkflowList } from './pages/WorkflowList'
import { WorkflowDetail } from './pages/WorkflowDetail'
import { WorkflowDesigner } from './pages/WorkflowDesigner'
import { RunMonitor } from './pages/RunMonitor'
import { AdminDashboard } from './pages/AdminDashboard'

const App: React.FC = () => {
  return (
    <div className="app">
      <nav className="navbar">
        <div className="nav-brand">
          <h1>🔄 Workflow System</h1>
        </div>
        <div className="nav-links">
          <a href="#/workflows">Workflows</a>
          <a href="#/admin">Admin</a>
        </div>
      </nav>
      
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/workflows" replace />} />
          <Route path="/workflows" element={<WorkflowList />} />
          <Route path="/workflows/:id" element={<WorkflowDetail />} />
          <Route path="/workflows/:id/design" element={<WorkflowDesigner />} />
          <Route path="/runs/:runId" element={<RunMonitor />} />
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
