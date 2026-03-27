import { useState, useRef, useEffect } from 'react'
import { sendMessage } from '../services/api'
import './Chat.css'

export default function Chat() {
  const [messages, setMessages] = useState([
    {
      role: 'ai',
      text: "Hi! I'm your AI banking assistant. I'll remember what you tell me so you don't have to repeat yourself.",
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setMessages((prev) => [...prev, { role: 'user', text }])
    setInput('')
    setLoading(true)

    try {
      const response = await sendMessage(text)
      setMessages((prev) => [...prev, { role: 'ai', text: response }])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'ai', text: 'Something went wrong. Please try again.' },
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
      {/* ── Header ──────────────────────────────────── */}
      <header className="chat-header">
        <div className="chat-header-left">
          <div className="chat-header-icon">
            <span className="material-symbols-outlined">neurology</span>
          </div>
          <div>
            <h1 className="chat-header-title">MemBridge AI</h1>
            <p className="chat-header-sub">Remembers your context across conversations</p>
          </div>
        </div>
        <div className="chat-header-right">
          <div className="status-badge">
            <span className="status-dot" />
            <span className="status-label">Memory Active</span>
          </div>
          <div className="avatar">
            <span
              className="material-symbols-outlined"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              account_circle
            </span>
          </div>
        </div>
      </header>

      {/* ── Messages ────────────────────────────────── */}
      <div className="chat-messages custom-scrollbar" id="chat-messages">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`msg-row ${msg.role === 'user' ? 'msg-user' : 'msg-ai'}`}
            style={{ animationDelay: `${i * 50}ms` }}
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
              onClick={handleSend}
              disabled={loading || !input.trim()}
              aria-label="Send message"
            >
              <span className="material-symbols-outlined">arrow_upward</span>
            </button>
          </div>
          <div className="chat-privacy">
            <span className="material-symbols-outlined">lock</span>
            <p>Your data stays on this device</p>
          </div>
        </div>
      </div>

      {/* ── Background glow ─────────────────────────── */}
      <div className="bg-decor" aria-hidden="true">
        <div className="glow glow-primary" />
        <div className="glow glow-tertiary" />
      </div>
    </div>
  )
}
