import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { BrandingHeader } from './Branding'

const API_URL = '/api'

export const roleDefaultPath = (role: string): string => {
  switch (role) {
    case 'admin': return '/admin'
    case 'developer': return '/workflows'
    case 'cmdb_manager': return '/cmdb'
    case 'staff': return '/tasks'
    case 'user': return '/portal'
    default: return '/workflows'
  }
}

interface User {
  id: number
  username: string
  email: string
  role: string
  full_name: string
  groups: Array<{id: number, name: string}>
}

interface AuthState {
  isAuthenticated: boolean
  user: User | null
  token: string | null
}

interface AuthContextType {
  isAuthenticated: boolean
  user: User | null
  token: string | null
  initializing: boolean
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string; user?: User }>
  register: (username: string, email: string, password: string, full_name?: string) => Promise<{ success: boolean; error?: string }>
  logout: () => void
}

const AuthContext = React.createContext<AuthContextType | null>(null)

export const useAuth = () => {
  const context = React.useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

const decodeJwtExp = (token: string): number | null => {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = JSON.parse(atob(parts[1]))
    return payload.exp ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

export const AuthProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    token: null
  })
  const [initializing, setInitializing] = useState(() => !!localStorage.getItem('token'))
  const refreshTimerRef = useRef<number | null>(null)

  useEffect(() => {
    // Check for existing token
    const token = localStorage.getItem('token')
    if (token) {
      setInitializing(true)
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
      fetchCurrentUser(token).finally(() => setInitializing(false))
    }
  }, [])

  // Proactive token refresh: schedule a /auth/me ping before expiry
  useEffect(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = null
    }
    if (!authState.token) return

    const exp = decodeJwtExp(authState.token)
    if (!exp) return

    const now = Date.now()
    const timeUntilExpiry = exp - now
    // Refresh 10 minutes before expiry, or immediately if < 10 min left
    const refreshIn = Math.max(0, timeUntilExpiry - 10 * 60 * 1000)

    if (refreshIn > 0) {
      refreshTimerRef.current = window.setTimeout(async () => {
        try {
          await axios.get(`${API_URL}/auth/me`, {
            headers: { Authorization: `Bearer ${authState.token}` }
          })
          // Token still valid, schedule next refresh
          setAuthState(prev => ({ ...prev }))
        } catch {
          // Token expired, clear it
          logout()
        }
      }, refreshIn)
    }
  }, [authState.token])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current)
      }
    }
  }, [])

  const fetchCurrentUser = async (token: string) => {
    try {
      const response = await axios.get(`${API_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setAuthState({
        isAuthenticated: true,
        user: response.data,
        token
      })
    } catch (error) {
      logout()
    }
  }

  const login = async (username: string, password: string) => {
    try {
      const formData = new URLSearchParams()
      formData.append('username', username)
      formData.append('password', password)

      const response = await axios.post(`${API_URL}/auth/login`, formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })

      const { access_token, user } = response.data
      
      localStorage.setItem('token', access_token)
      axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
      
      setAuthState({
        isAuthenticated: true,
        user,
        token: access_token
      })
      
      return { success: true, user }
    } catch (error: any) {
      return { 
        success: false, 
        error: error.response?.data?.detail || 'Login failed' 
      }
    }
  }

  const register = async (username: string, email: string, password: string, full_name?: string) => {
    try {
      const response = await axios.post(`${API_URL}/auth/register`, null, {
        params: { username, email, password, full_name }
      })
      return { success: true, user: response.data.user }
    } catch (error: any) {
      return { 
        success: false, 
        error: error.response?.data?.detail || 'Registration failed' 
      }
    }
  }

  const logout = () => {
    localStorage.removeItem('token')
    delete axios.defaults.headers.common['Authorization']
    setAuthState({
      isAuthenticated: false,
      user: null,
      token: null
    })
  }

  return (
    <AuthContext.Provider value={{
      ...authState,
      initializing,
      login,
      register,
      logout
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const LoginForm: React.FC = () => {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    const result = await login(username, password)
    
    if (result.success) {
      navigate(result.user ? roleDefaultPath(result.user.role) : '/workflows')
    } else {
      setError(result.error || 'Login failed')
    }
    setLoading(false)
  }

  return (
    <div style={{ maxWidth: '400px', margin: '2rem auto' }}>
      <BrandingHeader subtitle="Sign in to your account" />
      <div className="card">
        <h2 className="card-title">Login</h2>
        {error && <div className="error">{error}</div>}
        <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="form-input"
                value={username || ''}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                className="form-input"
                value={password || ''}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  )
}

export const RegisterForm: React.FC = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    full_name: ''
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const { register } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    
    const result = await register(formData.username, formData.email, formData.password, formData.full_name)
    
    if (result.success) {
      setSuccess(true)
    } else {
      setError(result.error || 'Registration failed')
    }
  }

  if (success) {
    return (
      <div style={{ maxWidth: '400px', margin: '2rem auto' }}>
        <BrandingHeader />
        <div className="card">
          <h2 className="card-title">Registration Successful</h2>
          <p>You can now log in with your credentials.</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '400px', margin: '2rem auto' }}>
      <BrandingHeader subtitle="Create your account" />
      <div className="card">
        <h2 className="card-title">Register</h2>
        {error && <div className="error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Full Name</label>
            <input
              type="text"
              className="form-input"
              value={formData.full_name}
              onChange={(e) => setFormData({...formData, full_name: e.target.value})}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Username</label>
            <input
              type="text"
              className="form-input"
              value={formData.username}
              onChange={(e) => setFormData({...formData, username: e.target.value})}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input
              type="email"
              className="form-input"
              value={formData.email}
              onChange={(e) => setFormData({...formData, email: e.target.value})}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-input"
              value={formData.password}
              onChange={(e) => setFormData({...formData, password: e.target.value})}
              required
            />
          </div>
          <button type="submit" className="btn btn-success" style={{ width: '100%' }}>
            Register
          </button>
        </form>
      </div>
    </div>
  )
}
