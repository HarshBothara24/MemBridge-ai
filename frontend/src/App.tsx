import { useState, useEffect, useCallback } from 'react'
import TopBar from './components/TopBar'
import CustomerProfile from './components/CustomerProfile'
import Chat from './components/Chat'
import MemoryTimeline from './components/MemoryTimeline'
import { fetchProfile, fetchTimeline } from './services/api'

function App() {
  const [customerId, setCustomerId] = useState<string>(() => {
    return localStorage.getItem('membridge_user_id') || ''
  })
  const [loginInput, setLoginInput] = useState('')

  function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    const id = loginInput.trim()
    if (!id) return
    localStorage.setItem('membridge_user_id', id)
    setCustomerId(id)
  }

  function handleCustomerChange(id: string) {
    localStorage.setItem('membridge_user_id', id)
    setCustomerId(id)
  }

  if (!customerId) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <span className="material-symbols-outlined login-icon">neurology</span>
          <h2>MemBridge AI</h2>
          <p>Enter your Customer ID to continue</p>
          <form onSubmit={handleLogin}>
            <input
              className="login-input"
              value={loginInput}
              onChange={(e) => setLoginInput(e.target.value)}
              placeholder="e.g. user_001"
              autoFocus
            />
            <button className="login-btn" type="submit">Continue</button>
          </form>
        </div>
      </div>
    )
  }
  const [profile, setProfile] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [memoryVersion, setMemoryVersion] = useState(0)

  // Fetch profile and timeline data
  const refreshMemory = useCallback(async () => {
    try {
      const [profileData, timelineData] = await Promise.all([
        fetchProfile(customerId),
        fetchTimeline(customerId),
      ])
      setProfile(profileData)
      setTimeline(timelineData)
    } catch (err) {
      console.error('Failed to refresh memory:', err)
    }
  }, [customerId])

  useEffect(() => {
    refreshMemory()
  }, [refreshMemory, memoryVersion])

  // Called after each chat message to refresh panels
  const onMemoryUpdate = () => {
    setMemoryVersion((v) => v + 1)
  }

  return (
    <div className="app-layout">
      <TopBar
        customerId={customerId}
        onCustomerChange={handleCustomerChange}
        totalFacts={profile?.total_facts || 0}
      />
      <div className="app-body">
        <CustomerProfile profile={profile} customerId={customerId} />
        <Chat
          customerId={customerId}
          onMemoryUpdate={onMemoryUpdate}
        />
        <MemoryTimeline timeline={timeline} />
      </div>
    </div>
  )
}

export default App
