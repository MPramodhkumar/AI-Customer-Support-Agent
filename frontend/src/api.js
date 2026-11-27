const BASE_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

async function request(path, key, options = {}) {
  let res
  try {
    const headers = {
      'Content-Type': 'application/json',
      ...(key ? { 'X-API-Key': key } : {}),
      ...options.headers,
    }
    res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  } catch {
    throw new Error("Can't reach the server. Check that the backend is running.")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const me = (key) => request('/me', key)
export const customers = () => request('/customers')
export const demoAccount = () => request('/demo')
export const register = (data) => request('/users', null, { method: 'POST', body: JSON.stringify(data) })
export const login = (data) => request('/login', null, { method: 'POST', body: JSON.stringify(data) })
export const orders = (key) => request('/orders', key)
export const createOrder = (key, data) => request('/orders', key, { method: 'POST', body: JSON.stringify(data) })
export const markDelivered = (key, id) => request(`/orders/${id}/deliver`, key, { method: 'POST' })
export const chat = (key, sessionId, message) =>
  request('/chat', key, { method: 'POST', body: JSON.stringify({ session_id: sessionId, message }) })