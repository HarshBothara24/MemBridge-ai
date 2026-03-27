import './Sidebar.css'

const navItems = [
  { icon: 'chat',            label: 'Conversations', active: true },
  { icon: 'account_balance', label: 'Wealth' },
  { icon: 'analytics',       label: 'Insights' },
  { icon: 'settings',        label: 'Settings' },
]

export default function Sidebar() {
  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <span className="material-symbols-outlined">neurology</span>
        </div>
        <div>
          <h2 className="sidebar-title">MemBridge</h2>
          <p className="sidebar-subtitle">Private Banking AI</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <a
            key={item.label}
            href="#"
            className={`sidebar-link${item.active ? ' active' : ''}`}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            <span>{item.label}</span>
          </a>
        ))}
      </nav>

      {/* Bottom action */}
      <div className="sidebar-footer">
        <button className="sidebar-new-btn">
          <span className="material-symbols-outlined">add</span>
          New Analysis
        </button>
      </div>
    </aside>
  )
}
