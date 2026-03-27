import { useState, useRef, useEffect } from 'react'
import { sendMessage } from '../services/api'
import './Chat.css'

const FACT_LABELS = {
  income: '💰 Income',
  loan_type: '🏦 Loan Type',
  loan_amount: '💵 Loan Amount',
  co_applicant: '👥 Co-Applicant',
  co_applicant_income: '💰 Co-Applicant Income',
  employment: '💼 Employment',
  credit_score: '📊 Credit Score',
  age: '🎂 Age',
  documents: '📄 Documents',
  property: '🏠 Property',
  property_location: '📍 Location',
}

function formatFactValue(key, value) {
  if (['income', 'loan_amount', 'co_applicant_income'].includes(key)) {
    const num = parseInt(value.replace(/,/g, ''), 10)
    if (!isNaN(num)) {
      if (num >= 10000000) return `₹${(num / 10000000).toFixed(1)}Cr`
      if (num >= 100000) return `₹${(num / 100000).toFixed(1)}L`
      return `₹${num.toLocaleString('en-IN')}`
    }
  }
  return value
}

export default function Chat({ customerId, onMemoryUpdate }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Reset messages when customer changes
  useEffect(() => {
    setMessages([])
    setSuggestions([])
  }, [customerId])

  async function handleSend(text) {
    const msg = (text || input).trim()
    if (!msg || loading) return

    setMessages((prev) => [...prev, { role: 'user', text: msg, facts: [] }])
    setInput('')
    setLoading(true)

    try {
      const data = await sendMessage(msg, customerId)
      setMessages((prev) => [
        // Update last user message with extracted facts
        ...prev.slice(0, -1),
        { ...prev[prev.length - 1], facts: data.extracted_facts || [] },
        { role: 'ai', text: data.response, facts: [] },
      ])
      setSuggestions(data.suggestions || [])

      // Notify parent to refresh memory panels
      if (onMemoryUpdate) onMemoryUpdate()
    } catch (err) {
      console.error('Chat error:', err)
      setMessages((prev) => [
        ...prev,
        { role: 'ai', text: 'Something went wrong. Please try again.', facts: [] },
      ])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="chat-canvas">
      {/* ── Messages ────────────────────────────────── */}
      <div className="chat-messages custom-scrollbar" id="chat-messages">
        {/* Welcome card when no messages */}
        {messages.length === 0 && (
          <div className="welcome-card">
            <div className="welcome-icon">
              <span className="material-symbols-outlined">neurology</span>
            </div>
            <h2>Welcome to MemBridge AI</h2>
            <p>
              I'm your intelligent banking assistant. I remember everything you tell me — across sessions and interactions.
              Try telling me about your income, loan needs, or ask about eligibility.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i}>
            <div
              className={`msg-row ${msg.role === 'user' ? 'msg-user' : 'msg-ai'}`}
              style={{ animationDelay: `${i * 40}ms` }}
            >
              {msg.role === 'ai' && (
                <div className="msg-avatar">
                  <span className="material-symbols-outlined">smart_toy</span>
                </div>
              )}

              <div className="msg-content">
                <div className={`msg-bubble ${msg.role}`}>{msg.text}</div>
                <span className="msg-time">
                  {msg.role === 'user' ? 'SENT' : formatTime()}
                </span>
              </div>
            </div>

            {/* Fact highlight pills below user messages */}
            {msg.role === 'user' && msg.facts && msg.facts.length > 0 && (
              <div className="fact-pills" style={{ justifyContent: 'flex-end', marginTop: '4px' }}>
                {msg.facts.map((fact, j) => (
                  <span key={j} className="fact-pill" style={{ animationDelay: `${j * 80}ms` }}>
                    <span className="pill-icon">📌</span>
                    {FACT_LABELS[fact.key] || fact.key}: {formatFactValue(fact.key, fact.value)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div className="msg-row msg-ai">
            <div className="msg-avatar msg-avatar-dim">
              <span className="material-symbols-outlined">smart_toy</span>
            </div>
            <div className="typing-indicator">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Suggestions ──────────────────────────────── */}
      {suggestions.length > 0 && !loading && (
        <div className="suggestions-area">
          {suggestions.map((s, i) => (
            <div
              key={i}
              className="suggestion-card"
              style={{ animationDelay: `${i * 100}ms` }}
              onClick={() => handleSend(s)}
            >
              <div className="suggestion-icon">
                <span className="material-symbols-outlined">lightbulb</span>
              </div>
              <span className="suggestion-text">{s}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Input ───────────────────────────────────── */}
      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <div className="chat-input-group">
            <input
              ref={inputRef}
              id="chat-input"
              type="text"
              placeholder="Ask about loans, income, or eligibility..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              id="send-button"
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
              aria-label="Send message"
            >
              <span className="material-symbols-outlined">arrow_upward</span>
            </button>
          </div>
          <div className="chat-privacy">
            <span className="material-symbols-outlined">lock</span>
            <p>All data stays on this device — no external APIs</p>
          </div>
        </div>
      </div>
    </div>
  )
}
