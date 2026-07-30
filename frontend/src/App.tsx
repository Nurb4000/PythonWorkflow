import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import axios from 'axios'
import { AuthProvider, useAuth, LoginForm, RegisterForm } from './components/Auth'
import { WorkflowList } from './pages/WorkflowList'
import { WorkflowDetail } from './pages/WorkflowDetail'
import { WorkflowDesigner } from './pages/WorkflowDesigner'
import { RunMonitor } from './pages/RunMonitor'
import { AdminDashboard } from './pages/AdminDashboard'
import { UserManagement } from './pages/UserManagement'
import { FormDesigner } from './pages/FormDesigner'
import { SettingsPage } from './pages/SettingsPage'

const API_URL = '/api'

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

const SetupCheck: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const [setupRequired, setSetupRequired] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkSetup()
  }, [])

  const checkSetup = async () => {
    try {
      const token = localStorage.getItem('token')
      if (token) {
        setLoading(false)
        return
      }
      
      const response = await axios.get(`${API_URL}/auth/setup-required`)
      setSetupRequired(response.data.setup_required)
    } catch (error) {
      console.error('Failed to check setup status:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Checking setup...</div>
  }

  if (setupRequired) {
    return <RegisterForm />
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
              <Link to="/workflows">Workflows</Link>
              <Link to="/admin">Admin</Link>
              {user.role === 'admin' && <Link to="/admin/users">Users</Link>}
              <Link to="/forms">Forms</Link>
              {user.role === 'admin' && <Link to="/settings">Settings</Link>}
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
          <Route path="/register" element={<SetupCheck><RegisterForm /></SetupCheck>} />
          <Route path="/" element={<ProtectedRoute><Navigate to="/workflows" replace /></ProtectedRoute>} />
          <Route path="/workflows" element={<ProtectedRoute><WorkflowList /></ProtectedRoute>} />
          <Route path="/workflows/:id" element={<ProtectedRoute><WorkflowDetail /></ProtectedRoute>} />
          <Route path="/workflows/:id/design" element={<ProtectedRoute><WorkflowDesigner /></ProtectedRoute>} />
          <Route path="/runs/:runId" element={<ProtectedRoute><RunMonitor /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><UserManagement /></ProtectedRoute>} />
          <Route path="/forms" element={<ProtectedRoute><FormDesigner /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
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
