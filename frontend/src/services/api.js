import axios from 'axios'

const API_BASE = 'http://localhost:8000'

/**
 * Send a chat message and get full response with metadata (non-streaming).
 * Returns: { response, extracted_facts, intent, suggestions, language }
 */
export async function sendMessage(message, customerId) {
  const res = await axios.post(`${API_BASE}/chat`, {
    message,
    customer_id: customerId,
  })
  return res.data
}

/**
 * Send a chat message and stream the response token-by-token.
 *
 * @param {string} message - User message
 * @param {string} customerId - Customer ID
 * @param {function} onMeta - Called with metadata: { extracted_facts, intent, suggestions, language }
 * @param {function} onToken - Called with each token string as it arrives
 * @returns {Promise<string>} - Full response text when streaming completes
 */
export async function sendMessageStream(message, customerId, onMeta, onToken) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, customer_id: customerId }),
  })

  if (!res.ok) {
    throw new Error(`Stream request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let fullResponse = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Process complete lines (NDJSON — one JSON object per line)
    const lines = buffer.split('\n')
    buffer = lines.pop() // keep incomplete last line in buffer

    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const data = JSON.parse(line)

        if (data.type === 'meta') {
          // First chunk: metadata (facts, intent, suggestions, language)
          if (onMeta) onMeta(data)
        } else if (data.type === 'token') {
          if (data.done) {
            // Stream complete — full_response available
            fullResponse = data.full_response || fullResponse
          } else {
            // Append token
            fullResponse += data.token
            if (onToken) onToken(data.token)
          }
        }
      } catch (e) {
        console.warn('Failed to parse stream chunk:', line, e)
      }
    }
  }

  return fullResponse
}

/**
 * Fetch structured customer profile for the left panel.
 */
export async function fetchProfile(customerId) {
  const res = await axios.get(`${API_BASE}/memory/${customerId}/profile`)
  return res.data
}

/**
 * Fetch memory timeline for the right panel.
 */
export async function fetchTimeline(customerId, limit = 50) {
  const res = await axios.get(`${API_BASE}/memory/${customerId}/timeline`, {
    params: { limit },
  })
  return res.data.timeline || []
}

/**
 * Fetch memory recall suggestions.
 */
export async function fetchSuggestions(customerId, intent = 'general', lang = 'en') {
  const res = await axios.get(`${API_BASE}/memory/${customerId}/suggestions`, {
    params: { intent, lang },
  })
  return res.data.suggestions || []
}

/**
 * Fetch recent chat history (for session restore).
 */
export async function fetchHistory(customerId, limit = 20) {
  const res = await axios.get(`${API_BASE}/memory/${customerId}/history`, {
    params: { limit },
  })
  return res.data.history || []
}

/**
 * Send a voice recording to the /voice endpoint.
 * Returns: { transcription, text, audio_url, language, extracted_facts }
 */
export async function sendVoiceMessage(audioBlob, customerId, sessionId = null) {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'recording.webm')
  formData.append('customer_id', customerId)
  if (sessionId) formData.append('session_id', sessionId)

  const res = await fetch(`${API_BASE}/voice`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error(`Voice request failed: ${res.status}`)
  return res.json()
}
