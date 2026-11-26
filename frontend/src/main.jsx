import { Component } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

// Shows the error on screen instead of a blank page, so problems are easy to report.
class Boundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ padding: 32, fontFamily: 'sans-serif' }}>
        <h2>Something broke in the page</h2>
        <pre style={{ whiteSpace: 'pre-wrap', color: '#b00020' }}>{String(this.state.error?.stack || this.state.error)}</pre>
        <button onClick={() => location.reload()}>Reload</button>
      </div>
    )
  }
}

createRoot(document.getElementById('root')).render(<Boundary><App /></Boundary>)
