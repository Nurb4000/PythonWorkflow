import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth, LoginForm, RegisterForm } from './components/Auth'
import { WorkflowList } from './pages/WorkflowList'
import { WorkflowDetail } from './pages/WorkflowDetail'
import { WorkflowDesigner } from './pages/WorkflowDesigner'
import { RunMonitor } from './pages/RunMonitor'
import { AdminDashboard } from './pages/AdminDashboard'
import { UserManagement } from './pages/UserManagement'

const ProtectedRoute: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

const PublicRoute: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const { isAuthenticated } = useAuth()
  if (isAuthenticated) {
    return <Navigate to="/workflows" replace />
  }
  return <>{children}</>
}

const AppContent: React.FC = () => {
  const { user, logout } = useAuth()

  return (
    <div className="app">
      <nav className="navbar">
        <div className="nav-brand">
          <h1>🔄 Workflow System</h1>
        </div>
        <div className="nav-links">
          {user && (
            <>
              <a href="#/workflows">Workflows</a>
              <a href="#/admin">Admin</a>
              {user.role === 'admin' && <a href="#/admin/users">Users</a>}
              <span style={{ marginLeft: '1rem', opacity: 0.8 }}>
                {user.full_name || user.username} ({user.role})
              </span>
              <button onClick={logout} className="btn btn-sm btn-secondary" style={{ marginLeft: '1rem' }}>
                Logout
              </button>
            </>
          )}
        </div>
      </nav>
      
      <main className="main-content">
        <Routes>
          <Route path="/login" element={<PublicRoute><LoginForm /></PublicRoute>} />
          <Route path="/register" element={<PublicRoute><RegisterForm /></PublicRoute>} />
          <Route path="/" element={<ProtectedRoute><Navigate to="/workflows" replace /></ProtectedRoute>} />
          <Route path="/workflows" element={<ProtectedRoute><WorkflowList /></ProtectedRoute>} />
          <Route path="/workflows/:id" element={<ProtectedRoute><WorkflowDetail /></ProtectedRoute>} />
          <Route path="/workflows/:id/design" element={<ProtectedRoute><WorkflowDesigner /></ProtectedRoute>} />
          <Route path="/runs/:runId" element={<ProtectedRoute><RunMonitor /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><UserManagement /></ProtectedRoute>} />
        </Routes>
      </main>
    </div>
  )
}

const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
