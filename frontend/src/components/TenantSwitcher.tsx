import React from 'react'
import { useAuth } from './Auth'

interface TenantSwitcherProps {
  /** Max rendered width of the dropdown. */
  style?: React.CSSProperties
}

/**
 * Multi-tenancy switcher. Lets a user pick which of their tenants is active for the
 * session. The selection is persisted to localStorage and sent as the `X-Tenant-Id`
 * header on every request (see services/api.ts), so the backend scopes all queries to
 * the chosen tenant. Switching reloads the page so open pages re-fetch scoped data.
 *
 * Hidden entirely when the user belongs to a single tenant (nothing to switch between).
 */
export const TenantSwitcher: React.FC<TenantSwitcherProps> = ({ style }) => {
  const { tenants, activeTenantId, setActiveTenant } = useAuth()

  if (!tenants || tenants.length === 0) return null
  if (tenants.length === 1) return null

  const current = tenants.find((t) => t.id === activeTenantId) || tenants[0]

  return (
    <div
      className="tenant-switcher"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem',
        color: 'white',
        ...style,
      }}
    >
      {/* Simple organization/building glyph */}
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        style={{ opacity: 0.85 }}
      >
        <rect x="4" y="2" width="16" height="20" rx="2" />
        <path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01" />
      </svg>
      <select
        value={current?.id ?? ''}
        onChange={(e) => setActiveTenant(Number(e.target.value))}
        className="form-input"
        style={{
          backgroundColor: 'rgba(255,255,255,0.12)',
          color: 'white',
          border: '1px solid rgba(255,255,255,0.25)',
          borderRadius: '4px',
          padding: '0.3rem 0.5rem',
          maxWidth: '190px',
          cursor: 'pointer',
        }}
        aria-label="Active tenant"
      >
        {tenants.map((t) => (
          <option key={t.id} value={t.id} style={{ color: '#222' }}>
            {t.name}
          </option>
        ))}
      </select>
    </div>
  )
}

export default TenantSwitcher
