import axios from 'axios'

const API_BASE = 'http://localhost:8000'

/**
 * Send a chat message and get full response with metadata.
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
