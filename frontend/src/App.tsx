import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, Link, useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'
import { AuthProvider, useAuth, LoginForm, RegisterForm, roleDefaultPath } from './components/Auth'
import { BrandingProvider, useBranding } from './components/Branding'
import { WorkflowList } from './pages/WorkflowList'
import { WorkflowDetail } from './pages/WorkflowDetail'
import { WorkflowDesigner } from './pages/WorkflowDesigner'
import { RunMonitor } from './pages/RunMonitor'
import { AdminDashboard } from './pages/AdminDashboard'
import { WorkflowRunsAdmin } from './pages/WorkflowRunsAdmin'
import { AdminTaskDashboard } from './pages/AdminTaskDashboard'
import { RoleTaskDashboard } from './pages/RoleTaskDashboard'
import { TaskDetail } from './pages/TaskDetail'
import { Portal } from './pages/Portal'
import { UserManagement } from './pages/UserManagement'
import { FormDesigner } from './pages/FormDesigner'
import { SettingsPage } from './pages/SettingsPage'
import { FieldManager } from './pages/FieldManager'
import { DataExplorer } from './pages/DataExplorer'
import { WorkflowImportExport } from './pages/WorkflowImportExport'
import { SQLViewManager } from './pages/SQLViewManager'
import { Marketplace } from './pages/Marketplace'

const API_URL = '/api'

const ProtectedRoute: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

const RoleRoute: React.FC<{roles: string[]; children: React.ReactNode}> = ({ roles, children }) => {
  const { user } = useAuth()
  if (!user || !roles.includes(user.role)) {
    return <Navigate to={user ? roleDefaultPath(user.role) : '/login'} replace />
  }
  return <>{children}</>
}

const PublicRoute: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const { isAuthenticated, user } = useAuth()
  if (isAuthenticated) {
    return <Navigate to={user ? roleDefaultPath(user.role) : '/workflows'} replace />
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

const RoleAwareNav: React.FC = () => {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  if (!user) return null

  const handleFormsClick = (e: React.MouseEvent) => {
    e.preventDefault()
    if (location.pathname === '/forms') {
      navigate('/forms', { replace: true })
    } else {
      navigate('/forms')
    }
  }

  const isPowerUser = user.role === 'admin' || user.role === 'developer'
  const isStaffOrAdmin = user.role === 'admin' || user.role === 'staff'

  return (
    <>
      {isPowerUser && <Link to="/workflows">Workflows</Link>}
      {isStaffOrAdmin && <Link to="/tasks">Tasks</Link>}
      {user.role === 'user' && <Link to="/my-tasks">My Tasks</Link>}
      <Link to="/portal">Portal</Link>
      {(user.role === 'admin' || user.role === 'developer') && <a href="/forms" onClick={handleFormsClick} style={{ color: 'inherit', textDecoration: 'none', cursor: 'pointer' }}>Forms</a>}
      {user.role === 'admin' && <Link to="/admin">Dashboard</Link>}
      {user.role === 'admin' && <Link to="/admin/users">Users</Link>}
      {user.role === 'admin' && <Link to="/admin/runs">Runs</Link>}
      {user.role === 'admin' && <Link to="/settings">Settings</Link>}
{(user.role === 'admin' || user.role === 'developer') && <Link to="/admin/data">Data Explorer</Link>}
      {(user.role === 'admin' || user.role === 'developer') && <Link to="/admin/views">SQL Views</Link>}
      {(user.role === 'admin' || user.role === 'developer') && <Link to="/workflows/import">Import/Export</Link>}
      {(user.role === 'admin' || user.role === 'developer') && <Link to="/marketplace">Marketplace</Link>}
{user.role === 'admin' && <Link to="/admin/fields">Field Manager</Link>}
    </>
  )
}

const RoleDefault: React.FC = () => {
  const { user } = useAuth()
  const navigate = useNavigate()
  
  useEffect(() => {
    if (!user) return
    
    const target = roleDefaultPath(user.role)
    
    if (window.location.pathname === '/') {
      navigate(target, { replace: true })
    }
  }, [user, navigate])
  
  return null
}

const Navbar: React.FC = () => {
  const { branding } = useBranding()
  const { user, logout } = useAuth()
  const [showPwdModal, setShowPwdModal] = useState(false)
  const [pwdForm, setPwdForm] = useState({ old_password: '', new_password: '', confirm_password: '' })
  const [pwdMsg, setPwdMsg] = useState('')
  const [pwdLoading, setPwdLoading] = useState(false)

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault()
    setPwdMsg('')
    if (pwdForm.new_password !== pwdForm.confirm_password) {
      setPwdMsg('New passwords do not match')
      return
    }
    setPwdLoading(true)
    try {
      const token = localStorage.getItem('token')
      const res = await fetch('/api/auth/me/password', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to change password')
      setPwdMsg('Password changed successfully')
      setPwdForm({ old_password: '', new_password: '', confirm_password: '' })
      setTimeout(() => setShowPwdModal(false), 1500)
    } catch (err: any) {
      setPwdMsg(err.message || 'Failed to change password')
    } finally {
      setPwdLoading(false)
    }
  }

  return (
    <nav className="navbar">
      <div className="nav-brand">
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'white', textDecoration: 'none' }}>
          {branding.logo_url && (
            <img src={branding.logo_url} alt="logo" className="brand-logo" style={{ height: '32px' }} />
          )}
          <h1>{branding.system_name || 'Workflow System'}</h1>
        </Link>
      </div>
      <div className="nav-links">
        {user && (
          <>
            <RoleAwareNav />
            <span style={{ marginLeft: '1rem', opacity: 0.8 }}>
              {user.full_name || user.username} ({user.role})
            </span>
            <button onClick={() => setShowPwdModal(true)} className="btn btn-sm btn-secondary" style={{ marginLeft: '1rem' }}>
              Change Password
            </button>
            <button onClick={logout} className="btn btn-sm btn-secondary" style={{ marginLeft: '0.5rem' }}>
              Logout
            </button>
          </>
        )}
      </div>

      {showPwdModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => setShowPwdModal(false)}>
          <div className="card" style={{ maxWidth: '400px', width: '90%' }} onClick={e => e.stopPropagation()}>
            <h3 className="card-title">Change Password</h3>
            {pwdMsg && (
              <div style={{ marginBottom: '1rem', padding: '0.5rem', borderRadius: '4px', backgroundColor: pwdMsg.includes('successfully') ? '#d4edda' : '#f8d7da', color: pwdMsg.includes('successfully') ? '#155724' : '#721c24' }}>
                {pwdMsg}
              </div>
            )}
            <form onSubmit={handlePasswordChange}>
              <div className="form-group">
                <label className="form-label">Current Password</label>
                <input
                  type="password"
                  className="form-input"
                  value={pwdForm.old_password}
                  onChange={e => setPwdForm({ ...pwdForm, old_password: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">New Password</label>
                <input
                  type="password"
                  className="form-input"
                  value={pwdForm.new_password}
                  onChange={e => setPwdForm({ ...pwdForm, new_password: e.target.value })}
                  required
                  minLength={4}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Confirm New Password</label>
                <input
                  type="password"
                  className="form-input"
                  value={pwdForm.confirm_password}
                  onChange={e => setPwdForm({ ...pwdForm, confirm_password: e.target.value })}
                  required
                  minLength={4}
                />
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                <button type="submit" className="btn btn-primary" disabled={pwdLoading}>
                  {pwdLoading ? 'Changing...' : 'Change Password'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setShowPwdModal(false)}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </nav>
  )
}

const AppContent: React.FC = () => {
  const { user, isAuthenticated, initializing } = useAuth()

  if (initializing) {
    return <div className="loading">Loading...</div>
  }

  if (!isAuthenticated || !user) {
    return (
      <Routes>
        <Route path="/login" element={<PublicRoute><LoginForm /></PublicRoute>} />
        <Route path="/register" element={<SetupCheck><RegisterForm /></SetupCheck>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <div className="app">
      <Navbar />
      
      <main className="main-content">
        <Routes>
          <Route path="/" element={<ProtectedRoute><RoleDefault /></ProtectedRoute>} />
          <Route path="/workflows" element={<ProtectedRoute><WorkflowList /></ProtectedRoute>} />
          <Route path="/workflows/:id" element={<ProtectedRoute><WorkflowDetail /></ProtectedRoute>} />
          <Route path="/workflows/:id/design" element={<RoleRoute roles={['admin', 'developer']}><WorkflowDesigner /></RoleRoute>} />
          <Route path="/workflows/import" element={<RoleRoute roles={['admin', 'developer']}><WorkflowImportExport /></RoleRoute>} />
          <Route path="/runs/:runId" element={<ProtectedRoute><RunMonitor /></ProtectedRoute>} />
          <Route path="/admin" element={<RoleRoute roles={['admin']}><AdminDashboard /></RoleRoute>} />
          <Route path="/admin/users" element={<RoleRoute roles={['admin']}><UserManagement /></RoleRoute>} />
          <Route path="/admin/runs" element={<RoleRoute roles={['admin']}><WorkflowRunsAdmin /></RoleRoute>} />
          <Route path="/admin/tasks" element={<RoleRoute roles={['admin']}><AdminTaskDashboard /></RoleRoute>} />
          <Route path="/tasks" element={<RoleRoute roles={['admin', 'developer', 'staff']}><RoleTaskDashboard role="developer" title="Tasks" /></RoleRoute>} />
          <Route path="/my-tasks" element={<ProtectedRoute><RoleTaskDashboard role="user" title="My Tasks" /></ProtectedRoute>} />
          <Route path="/tasks/:id" element={<ProtectedRoute><TaskDetail /></ProtectedRoute>} />
          <Route path="/portal" element={<ProtectedRoute><Portal /></ProtectedRoute>} />
          <Route path="/forms" element={<ProtectedRoute><FormDesigner /></ProtectedRoute>} />
          <Route path="/settings" element={<RoleRoute roles={['admin']}><SettingsPage /></RoleRoute>} />
<Route path="/admin/data" element={<RoleRoute roles={['admin', 'developer']}><DataExplorer /></RoleRoute>} />
          <Route path="/admin/views" element={<RoleRoute roles={['admin', 'developer']}><SQLViewManager /></RoleRoute>} />
<Route path="/admin/fields" element={<RoleRoute roles={['admin']}><FieldManager /></RoleRoute>} />
          <Route path="/marketplace" element={<RoleRoute roles={['admin', 'developer']}><Marketplace /></RoleRoute>} />
          <Route path="/login" element={<Navigate to={roleDefaultPath(user.role)} replace />} />
          <Route path="*" element={<Navigate to={roleDefaultPath(user.role)} replace />} />
        </Routes>
      </main>
    </div>
  )
}

const App: React.FC = () => {
  return (
    <BrandingProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrandingProvider>
  )
}

export default App
