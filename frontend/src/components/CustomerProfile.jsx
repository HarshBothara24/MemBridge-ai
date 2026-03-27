import './CustomerProfile.css'

const FACT_CONFIG = {
  income:             { icon: '💰', label: 'Income',          iconClass: 'income' },
  loan_type:          { icon: '🏦', label: 'Loan Type',       iconClass: 'loan' },
  loan_amount:        { icon: '💵', label: 'Loan Amount',     iconClass: 'loan' },
  co_applicant:       { icon: '👥', label: 'Co-Applicant',    iconClass: 'person' },
  co_applicant_income:{ icon: '💰', label: 'Co-Applicant Income', iconClass: 'income' },
  employment:         { icon: '💼', label: 'Employment',      iconClass: 'work' },
  credit_score:       { icon: '📊', label: 'Credit Score',    iconClass: 'score' },
  age:                { icon: '🎂', label: 'Age',             iconClass: 'age' },
  documents:          { icon: '📄', label: 'Documents',       iconClass: 'document' },
  property:           { icon: '🏠', label: 'Property',        iconClass: 'property' },
  property_location:  { icon: '📍', label: 'Property Location', iconClass: 'property' },
}

function formatValue(key, value) {
  const raw = typeof value === 'string' ? value : JSON.stringify(value)
  // strip extra quotes from JSONB strings
  const clean = raw.replace(/^"|"$/g, '')

  // Format currency values
  if (['income', 'loan_amount', 'co_applicant_income'].includes(key)) {
    const num = parseInt(clean.replace(/,/g, ''), 10)
    if (!isNaN(num)) {
      if (num >= 10000000) return `₹${(num / 10000000).toFixed(1)}Cr`
      if (num >= 100000) return `₹${(num / 100000).toFixed(1)}L`
      return `₹${num.toLocaleString('en-IN')}`
    }
  }

  if (key === 'co_applicant' && clean.toLowerCase() === 'yes') return 'Yes ✓'
  return clean
}

function getConfidenceLevel(confidence) {
  if (confidence >= 0.8) return 'high'
  if (confidence >= 0.5) return 'medium'
  return 'low'
}

function getTimeAgo(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export default function CustomerProfile({ profile, customerId }) {
  const facts = profile?.facts || {}
  const factEntries = Object.entries(facts)

  return (
    <aside className="customer-profile" id="customer-profile">
      {/* Header */}
      <div className="profile-header">
        <div className="profile-avatar-row">
          <div className="profile-avatar">
            <span className="material-symbols-outlined">account_circle</span>
          </div>
          <div>
            <div className="profile-name">Customer</div>
            <div className="profile-id">{customerId}</div>
          </div>
        </div>
        <div className="profile-status">
          <span className="profile-status-dot" />
          Memory Active
        </div>
      </div>

      {/* Facts */}
      <div className="profile-section-title">Key Memory</div>
      <div className="profile-facts custom-scrollbar">
        {factEntries.length === 0 ? (
          <div className="profile-empty">
            <span className="material-symbols-outlined">psychology</span>
            <p>No memories yet.<br />Start a conversation to build context.</p>
          </div>
        ) : (
          factEntries.map(([key, fact], idx) => {
            const config = FACT_CONFIG[key] || { icon: '📌', label: key.replace(/_/g, ' '), iconClass: 'default' }
            const level = getConfidenceLevel(fact.confidence)

            return (
              <div
                key={key}
                className={`fact-card ${level}-confidence`}
                style={{ animationDelay: `${idx * 60}ms` }}
              >
                <div className={`fact-icon ${config.iconClass}`}>
                  {config.icon}
                </div>
                <div className="fact-body">
                  <div className="fact-label">{config.label}</div>
                  <div className="fact-value">{formatValue(key, fact.value)}</div>
                  <div className="fact-meta">
                    <span className="fact-time">{getTimeAgo(fact.updated_at)}</span>
                    {fact.version > 1 && (
                      <span className="fact-version">v{fact.version}</span>
                    )}
                  </div>
                  <div className="confidence-bar">
                    <div
                      className={`confidence-fill ${level}`}
                      style={{ width: `${Math.round(fact.confidence * 100)}%` }}
                    />
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
