import { useState } from 'react'
import './TopBar.css'

export default function TopBar({ customerId, onCustomerChange, totalFacts }) {
  const [editing, setEditing] = useState(false)
  const [tempId, setTempId] = useState(customerId)

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = tempId.trim()
    if (trimmed) {
      onCustomerChange(trimmed)
    }
    setEditing(false)
  }

  return (
    <header className="topbar" id="topbar">
      {/* Left — Brand */}
      <div className="topbar-left">
        <div className="topbar-logo">
          <span className="material-symbols-outlined">neurology</span>
        </div>
        <div className="topbar-brand">
          <h1>MemBridge AI</h1>
          <p>Cognitive Banking</p>
        </div>
      </div>

      {/* Center — Status */}
      <div className="topbar-center">
        <div className="topbar-badge">
          <span className="sync-dot" />
          <span>Memory synced across sessions</span>
        </div>
        <div className="topbar-badge">
          <span className="material-symbols-outlined">psychology</span>
          <span>Agent Active</span>
        </div>
      </div>

      {/* Right — Customer + Facts */}
      <div className="topbar-right">
        {totalFacts > 0 && (
          <div className="fact-counter">
            <span className="material-symbols-outlined">database</span>
            <span>{totalFacts} memories</span>
          </div>
        )}
        <div className="customer-selector">
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>person</span>
          {editing ? (
            <form onSubmit={handleSubmit} style={{ display: 'inline' }}>
              <input
                className="customer-input"
                value={tempId}
                onChange={(e) => setTempId(e.target.value)}
                onBlur={handleSubmit}
                autoFocus
                placeholder="Customer ID"
              />
            </form>
          ) : (
            <span
              onClick={() => { setEditing(true); setTempId(customerId); }}
              style={{ cursor: 'pointer' }}
            >
              {customerId}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
