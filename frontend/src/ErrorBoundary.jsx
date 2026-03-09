import { Component } from 'react'

/**
 * Catches React render errors and shows a message instead of a blank white page.
 */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Dashboard error:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: 24,
          fontFamily: 'system-ui, sans-serif',
          maxWidth: 560,
          margin: '40px auto',
          background: '#fff',
          borderRadius: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        }}>
          <h2 style={{ color: '#c62828', marginBottom: 12 }}>Dashboard error</h2>
          <pre style={{
            overflow: 'auto',
            padding: 12,
            background: '#f5f5f5',
            borderRadius: 4,
            fontSize: 13,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {this.state.error?.message ?? String(this.state.error)}
          </pre>
          <p style={{ marginTop: 12, color: '#666', fontSize: 14 }}>
            Check the browser console (F12 → Console) for more details.
          </p>
        </div>
      )
    }
    return this.props.children
  }
}
