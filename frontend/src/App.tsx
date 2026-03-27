import { useState, useEffect, useCallback } from 'react'
import TopBar from './components/TopBar'
import CustomerProfile from './components/CustomerProfile'
import Chat from './components/Chat'
import MemoryTimeline from './components/MemoryTimeline'
import { fetchProfile, fetchTimeline } from './services/api'

function App() {
  const [customerId, setCustomerId] = useState('user_001')
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
        onCustomerChange={setCustomerId}
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
