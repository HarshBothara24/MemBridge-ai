import axios from 'axios'

export async function sendMessage(message, customer_id = 'user_001') {
  const res = await axios.post('http://localhost:8000/chat', {
    message,
    customer_id,
  })
  return res.data.response
}
