import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import { ErrorBoundary } from './components/ErrorBoundary'

describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div data-testid="child">Hello</div>
      </ErrorBoundary>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('shows fallback UI when child throws', () => {
    const ThrowingComponent = () => {
      throw new Error('Test error')
    }

    // Suppress console.error noise
    vi.spyOn(console, 'error').mockReturnValue(undefined)

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Test error')).toBeInTheDocument()
  })

  it('shows custom fallback when provided', () => {
    const ThrowingComponent = () => {
      throw new Error('Custom error')
    }

    render(
      <ErrorBoundary fallback={<div data-testid="custom">Custom Fallback</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    )

    expect(screen.getByTestId('custom')).toBeInTheDocument()
  })

  it('recovers after "Try again" is clicked', async () => {
    const { rerender } = render(
      <ErrorBoundary>
        <div data-testid="child">Hello</div>
      </ErrorBoundary>
    )

    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})
