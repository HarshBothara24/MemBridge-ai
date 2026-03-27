import { useState, useRef, useEffect, useCallback } from 'react'
import { sendMessageStream, sendVoiceMessage } from '../services/api'
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
  const [streaming, setStreaming] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [recording, setRecording] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Reset messages when customer changes
  useEffect(() => {
    setMessages([])
    setSuggestions([])
  }, [customerId])

  const handleSend = useCallback(async (text) => {
    const msg = (text || input).trim()
    if (!msg || loading || streaming) return

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', text: msg, facts: [] }])
    setInput('')
    setLoading(true)

    try {
      // Add an empty AI message that we'll stream into
      setMessages((prev) => [
        ...prev,
        { role: 'ai', text: '', facts: [], isStreaming: true },
      ])
      setStreaming(true)
      setLoading(false) // hide typing dots, show streaming text instead

      const fullResponse = await sendMessageStream(
        msg,
        customerId,
        // onMeta: receive extracted facts, intent, suggestions, language
        (meta) => {
          // Update the user message with extracted facts
          setMessages((prev) => {
            const updated = [...prev]
            // Find the last user message (second to last in array)
            const userMsgIdx = updated.length - 2
            if (userMsgIdx >= 0 && updated[userMsgIdx].role === 'user') {
              updated[userMsgIdx] = {
                ...updated[userMsgIdx],
                facts: meta.extracted_facts || [],
              }
            }
            return updated
          })
          setSuggestions(meta.suggestions || [])
        },
        // onToken: append each token to the AI message
        (token) => {
          setMessages((prev) => {
            const updated = [...prev]
            const lastMsg = updated[updated.length - 1]
            if (lastMsg && lastMsg.role === 'ai') {
              updated[updated.length - 1] = {
                ...lastMsg,
                text: lastMsg.text + token,
              }
            }
            return updated
          })
        }
      )

      // Mark streaming as complete
      setMessages((prev) => {
        const updated = [...prev]
        const lastMsg = updated[updated.length - 1]
        if (lastMsg && lastMsg.role === 'ai') {
          updated[updated.length - 1] = {
            ...lastMsg,
            text: fullResponse || lastMsg.text,
            isStreaming: false,
          }
        }
        return updated
      })

      // Notify parent to refresh memory panels
      if (onMemoryUpdate) onMemoryUpdate()
    } catch (err) {
      console.error('Chat error:', err)
      setMessages((prev) => {
        // Remove the empty streaming message if it exists
        const updated = prev.filter((m) => !(m.role === 'ai' && m.isStreaming && !m.text))
        return [
          ...updated,
          { role: 'ai', text: 'Something went wrong. Please try again.', facts: [] },
        ]
      })
    } finally {
      setStreaming(false)
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [input, loading, streaming, customerId, onMemoryUpdate])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioChunksRef.current = []
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        await handleVoiceSend(blob)
      }

      recorder.start()
      setRecording(true)
    } catch (err) {
      console.error('Mic access denied:', err)
      alert('Microphone access is required for voice input.')
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop()
    setRecording(false)
  }

  async function handleVoiceSend(audioBlob) {
    setLoading(true)
    setMessages((prev) => [...prev, { role: 'user', text: '🎤 Voice message...', facts: [], isVoice: true }])

    try {
      const result = await sendVoiceMessage(audioBlob, customerId)

      if (result.error) throw new Error(result.error)

      // Update user message with transcription
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          text: result.transcription || '🎤 Voice message',
          facts: result.extracted_facts || [],
        }
        return updated
      })

      // Add AI response
      setMessages((prev) => [...prev, { role: 'ai', text: result.text, facts: [], isVoice: true, audioUrl: result.audio_url, language: result.language }])

      // Auto-play audio response
      if (result.audio_url) {
        const audio = new Audio(result.audio_url)
        audio.play().catch(() => {})
      }

      if (onMemoryUpdate) onMemoryUpdate()
    } catch (err) {
      console.error('Voice error:', err)
      setMessages((prev) => [...prev, { role: 'ai', text: 'Voice processing failed. Please try again.', facts: [] }])
    } finally {
      setLoading(false)
    }
  }

  function formatTime() {
    return new Date().toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Kolkata',
    })
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
                <div className={`msg-bubble ${msg.role}`}>
                  {msg.text}
                  {msg.isStreaming && <span className="streaming-cursor">▊</span>}
                </div>
                <span className="msg-time">
                  {msg.role === 'user' ? 'SENT' : formatTime()}
                </span>
                {msg.role === 'ai' && msg.isVoice && msg.audioUrl && (
                  <button
                    className="replay-btn"
                    onClick={() => new Audio(msg.audioUrl).play()}
                    title="Replay audio"
                  >
                    <span className="material-symbols-outlined">volume_up</span>
                  </button>
                )}
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

        {/* Typing indicator — only when waiting for first token */}
        {loading && !streaming && (
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
      {suggestions.length > 0 && !loading && !streaming && (
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
              disabled={loading || streaming || recording}
            />
            <button
              className={`mic-btn ${recording ? 'recording' : ''}`}
              onClick={recording ? stopRecording : startRecording}
              disabled={loading || streaming}
              aria-label={recording ? 'Stop recording' : 'Click to speak'}
              title={recording ? 'Click to stop' : 'Click to speak'}
            >
              <span className="material-symbols-outlined">
                {recording ? 'stop_circle' : 'mic'}
              </span>
            </button>
            <button
              id="send-button"
              onClick={() => handleSend()}
              disabled={loading || streaming || !input.trim() || recording}
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
