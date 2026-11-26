async function request(path, key, options = {}) {
  let res
  try {
    res = await fetch('/api' + path, { ...options, headers: { 'Content-Type': 'application/json', 'X-API-Key': key } })
  } catch {
    throw new Error("Can't reach the server. Check that the backend is running on port 8000.")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const me = (key) => request('/me', key)
export const chat = (key, sessionId, message) =>
  request('/chat', key, { method: 'POST', body: JSON.stringify({ session_id: sessionId, message }) })
