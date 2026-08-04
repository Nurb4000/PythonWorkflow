import React, { createContext, useContext, useEffect, useState } from 'react'
import axios from 'axios'

const API_URL = '/api'

export interface Branding {
  system_name: string
  portal_name: string
  logo_url: string | null
}

const DEFAULT_BRANDING: Branding = {
  system_name: 'Workflow System',
  portal_name: 'Submission Portal',
  logo_url: null
}

interface BrandingContextValue {
  branding: Branding
  refresh: () => Promise<void>
  ready: boolean
}

const BrandingContext = createContext<BrandingContextValue>({
  branding: DEFAULT_BRANDING,
  refresh: async () => {},
  ready: false
})

export const useBranding = () => useContext(BrandingContext)

export const BrandingProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [branding, setBranding] = useState<Branding>(DEFAULT_BRANDING)
  const [ready, setReady] = useState(false)

  const refresh = async () => {
    try {
      const res = await axios.get(`${API_URL}/branding`)
      setBranding(res.data as Branding)
    } catch {
      // keep defaults on error
    } finally {
      setReady(true)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    document.title = branding.system_name
  }, [branding.system_name])

  return (
    <BrandingContext.Provider value={{ branding, refresh, ready }}>
      {children}
    </BrandingContext.Provider>
  )
}

export const BrandingHeader: React.FC<{ subtitle?: string }> = ({ subtitle }) => {
  const { branding } = useBranding()
  return (
    <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
      {branding.logo_url && (
        <img src={branding.logo_url} alt={`${branding.system_name} logo`} className="brand-logo" />
      )}
      <h1 style={{ margin: '0 0 0.25rem', fontSize: '1.5rem' }}>{branding.system_name}</h1>
      {subtitle && <p style={{ margin: 0, color: '#7f8c8d' }}>{subtitle}</p>}
    </div>
  )
}
