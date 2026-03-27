import './MemoryTimeline.css'

const FACT_ICONS = {
  income:             { icon: '💰', className: 'income' },
  loan_type:          { icon: '🏦', className: 'loan' },
  loan_amount:        { icon: '💵', className: 'loan' },
  co_applicant:       { icon: '👥', className: 'person' },
  co_applicant_income:{ icon: '💰', className: 'income' },
  employment:         { icon: '💼', className: 'work' },
  credit_score:       { icon: '📊', className: 'score' },
  age:                { icon: '🎂', className: 'age' },
  documents:          { icon: '📄', className: 'document' },
  property:           { icon: '🏠', className: 'property' },
  property_location:  { icon: '📍', className: 'property' },
}

function formatValue(key, value) {
  const raw = typeof value === 'string' ? value : JSON.stringify(value)
  const clean = raw.replace(/^"|"$/g, '')

  if (['income', 'loan_amount', 'co_applicant_income'].includes(key)) {
    const num = parseInt(clean.replace(/,/g, ''), 10)
    if (!isNaN(num)) {
      if (num >= 10000000) return `₹${(num / 10000000).toFixed(1)}Cr`
      if (num >= 100000) return `₹${(num / 100000).toFixed(1)}L`
      return `₹${num.toLocaleString('en-IN')}`
    }
  }

  if (key === 'co_applicant' && clean.toLowerCase() === 'yes') return 'Added ✓'
  return clean
}

function getConfidenceLevel(confidence) {
  if (confidence >= 0.8) return 'high'
  if (confidence >= 0.5) return 'medium'
  return 'low'
}

function formatDate(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  return date.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function getRelativeDay(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diffDays = Math.floor((now - date) / 86400000)

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) {
    return date.toLocaleDateString('en-IN', { weekday: 'long' })
  }
  return formatDate(isoString)
}

function groupByDate(timeline) {
  const groups = {}
  for (const item of timeline) {
    const dateStr = item.created_at ? new Date(item.created_at).toDateString() : 'Unknown'
    if (!groups[dateStr]) {
      groups[dateStr] = {
        label: getRelativeDay(item.created_at),
        items: [],
      }
    }
    groups[dateStr].items.push(item)
  }
  return Object.values(groups)
}

export default function MemoryTimeline({ timeline }) {
  const groups = groupByDate(timeline || [])

  return (
    <aside className="memory-timeline" id="memory-timeline">
      {/* Header */}
      <div className="timeline-header">
        <div className="timeline-header-row">
          <div className="timeline-header-icon">
            <span className="material-symbols-outlined">timeline</span>
          </div>
          <h2>Memory Timeline</h2>
        </div>
        <p>Chronological history of extracted facts</p>
      </div>

      {/* Content */}
      <div className="timeline-content custom-scrollbar">
        {groups.length === 0 ? (
          <div className="timeline-empty">
            <span className="material-symbols-outlined">history</span>
            <p>No memories recorded yet.<br />Facts will appear here as you chat.</p>
          </div>
        ) : (
          <>
            <div className="timeline-live">
              <span className="timeline-live-dot" />
              LIVE
            </div>

            {groups.map((group, gi) => (
              <div key={gi}>
                {/* Date separator */}
                <div className="timeline-date">
                  <span className="timeline-date-label">{group.label}</span>
                  <span className="timeline-date-line" />
                </div>

                {/* Items */}
                {group.items.map((item, ii) => {
                  const config = FACT_ICONS[item.key] || { icon: '📌', className: 'default' }
                  const isActive = item.status === 'active'
                  const level = getConfidenceLevel(item.confidence)

                  return (
                    <div
                      key={item.id || `${gi}-${ii}`}
                      className="timeline-item"
                      style={{ animationDelay: `${(gi * 3 + ii) * 60}ms` }}
                    >
                      <div className="timeline-dot-wrap">
                        <div className={`timeline-dot ${config.className} ${isActive ? 'active' : 'superseded'}`}>
                          {config.icon}
                        </div>
                      </div>

                      <div className="timeline-body">
                        <div className="timeline-fact-key">
                          {item.key?.replace(/_/g, ' ')}
                        </div>
                        <div className="timeline-fact-value" style={!isActive ? { textDecoration: 'line-through', opacity: 0.5 } : {}}>
                          {formatValue(item.key, item.value)}
                        </div>
                        <div className="timeline-fact-meta">
                          <span className="timeline-time">
                            {formatTime(item.created_at)}
                          </span>
                          <span className={`timeline-status ${isActive ? 'active' : 'superseded'}`}>
                            {isActive ? 'Active' : 'Superseded'}
                          </span>
                          {item.version > 1 && (
                            <span className="timeline-version">v{item.version}</span>
                          )}
                          <span className={`confidence-dot ${level}`} title={`Confidence: ${Math.round(item.confidence * 100)}%`} />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </>
        )}
      </div>
    </aside>
  )
}
