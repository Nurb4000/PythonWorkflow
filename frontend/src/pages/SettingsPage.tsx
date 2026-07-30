import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_URL = '/api'

interface Settings {
  llama_cpp_url: string
  llama_cpp_model: string
  email_smtp_host: string
  email_smtp_port: number
  email_from: string
}

export const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<Settings>({
    llama_cpp_url: '',
    llama_cpp_model: 'default',
    email_smtp_host: '',
    email_smtp_port: 587,
    email_from: ''
  })
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/settings`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setSettings(response.data)
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleLLMUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      await axios.put(
        `${API_URL}/settings/llm`,
        null,
        {
          params: {
            llama_cpp_url: settings.llama_cpp_url,
            llama_cpp_model: settings.llama_cpp_model
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      setMessage('LLM settings updated successfully')
    } catch (error) {
      setMessage('Failed to update LLM settings')
    }
  }

  const handleEmailUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      await axios.put(
        `${API_URL}/settings/email`,
        null,
        {
          params: {
            smtp_host: settings.email_smtp_host,
            smtp_port: settings.email_smtp_port,
            username: '', // Don't send password for security
            from_address: settings.email_from
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      setMessage('Email settings updated successfully')
    } catch (error) {
      setMessage('Failed to update email settings')
    }
  }

  if (loading) {
    return <div className="loading">Loading settings...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>System Settings</h2>
      </div>

      {message && <div className="error" style={{ marginBottom: '1rem' }}>{message}</div>}

      <div className="card">
        <h3 className="card-title">LLM Configuration (llama.cpp)</h3>
        <form onSubmit={handleLLMUpdate}>
          <div className="form-group">
            <label className="form-label">llama.cpp Server URL</label>
            <input
              type="text"
              className="form-input"
              value={settings.llama_cpp_url}
              onChange={(e) => setSettings({...settings, llama_cpp_url: e.target.value})}
              placeholder="http://localhost:8081"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Model Name</label>
            <input
              type="text"
              className="form-input"
              value={settings.llama_cpp_model}
              onChange={(e) => setSettings({...settings, llama_cpp_model: e.target.value})}
              placeholder="default"
            />
          </div>
          <button type="submit" className="btn btn-success">Save LLM Settings</button>
        </form>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="card-title">Email Configuration</h3>
        <form onSubmit={handleEmailUpdate}>
          <div className="grid grid-2">
            <div className="form-group">
              <label className="form-label">SMTP Host</label>
              <input
                type="text"
                className="form-input"
                value={settings.email_smtp_host}
                onChange={(e) => setSettings({...settings, email_smtp_host: e.target.value})}
                placeholder="smtp.example.com"
              />
            </div>
            <div className="form-group">
              <label className="form-label">SMTP Port</label>
              <input
                type="number"
                className="form-input"
                value={settings.email_smtp_port}
                onChange={(e) => setSettings({...settings, email_smtp_port: parseInt(e.target.value)})}
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">From Address</label>
            <input
              type="email"
              className="form-input"
              value={settings.email_from}
              onChange={(e) => setSettings({...settings, email_from: e.target.value})}
              placeholder="noreply@example.com"
            />
          </div>
          <button type="submit" className="btn btn-success">Save Email Settings</button>
        </form>
      </div>
    </div>
  )
}
