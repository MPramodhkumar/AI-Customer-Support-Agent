import { useEffect, useRef, useState } from 'react'
import { chat, me } from './api'
import './styles.css'

const DEMO = [
  { key: 'key-aarav', name: 'Aarav Sharma', color: '#6C47FF', order: 1001, cancel: 1002, refund: 1003 },
  { key: 'key-priya', name: 'Priya Nair', color: '#FF6B6B', order: 1004, cancel: 1004, refund: 1004 },
]
const TOOL = {
  get_order_status: ['📦', 'Order lookup'],
  cancel_order: ['✂️', 'Cancel order'],
  check_refund_status: ['💸', 'Refund check'],
  create_support_ticket: ['🎫', 'Support ticket'],
  search_knowledge_base: ['📚', 'Help center'],
}
const STATUS = { success: 'Done', failed: 'Failed', needs_confirmation: 'Needs your OK', blocked: 'Blocked', skipped: 'Skipped' }

const fmt = (t) => t.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p))

function Login({ onLogin }) {
  const [key, setKey] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function go(k) {
    setBusy(true); setErr('')
    try {
      const profile = await me(k)
      onLogin({ key: k, ...profile, demo: DEMO.find((d) => d.key === k) || DEMO[0] })
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  return (
    <main className="login">
      <section className="hero">
        <div className="logo">✓ Checkr</div>
        <h1>Ask once. Get it done.</h1>
        <p>Track orders, cancel them, check refunds and reach a real person, all in one friendly chat.</p>
        <div className="floaters">
          <span style={{ '--c': '#6C47FF' }}>📦 Order #1001 shipped</span>
          <span style={{ '--c': '#12C99B' }}>💸 Refund on its way</span>
          <span style={{ '--c': '#FF6B6B' }}>🎫 Ticket opened</span>
        </div>
      </section>
      <section className="glass login-card">
        <h2>Choose who to chat as</h2>
        {DEMO.map((d) => (
          <button key={d.key} className="who" disabled={busy} onClick={() => go(d.key)}>
            <i style={{ background: d.color }}>{d.name[0]}</i>{d.name}
          </button>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); key && go(key) }}>
          <input placeholder="or paste an API key" value={key} onChange={(e) => setKey(e.target.value)} />
        </form>
        {err && <p className="err">{err}</p>}
      </section>
    </main>
  )
}

function Chat({ user, onLogout }) {
  const d = user.demo
  const [sessionId] = useState(() => crypto.randomUUID())
  const [msgs, setMsgs] = useState([{ role: 'bot', text: `Hi ${user.name.split(' ')[0]}! I'm Checkr. What can I sort out for you today?` }])
  const [activity, setActivity] = useState([])
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const feed = useRef(null)
  useEffect(() => { const f = feed.current; if (f) f.scrollTo({ top: f.scrollHeight, behavior: 'smooth' }) }, [msgs, busy])

  async function send(message) {
    message = message.trim()
    if (!message || busy) return
    setText(''); setBusy(true)
    setMsgs((m) => [...m, { role: 'me', text: message }])
    try {
      const r = await chat(user.key, sessionId, message)
      setMsgs((m) => [...m, { role: 'bot', text: r.reply, steps: r.steps, escalated: r.escalated }])
      setActivity((a) => [...r.steps.map((s, i) => ({ ...s, id: `${Date.now()}-${i}` })).reverse(), ...a])
    } catch (e) { setMsgs((m) => [...m, { role: 'bot', text: e.message, error: true }]) }
    setBusy(false)
  }

  const last = msgs[msgs.length - 1]
  const asking = last.role === 'bot' && last.steps?.find((s) => s.status === 'needs_confirmation')
  const calls = activity.filter((a) => a.status !== 'skipped').length
  const tickets = activity.filter((a) => a.tool === 'create_support_ticket' && a.status === 'success').length
  const quick = [
    ['📦', 'Track my order', `Where is my order ${d.order}?`, '#6C47FF'],
    ['✂️', 'Cancel an order', `I want to cancel order ${d.cancel}`, '#FF6B6B'],
    ['💸', 'Refund status', `What's the refund status for order ${d.refund}?`, '#12C99B'],
    ['📚', 'Return policy', 'What is your return policy?', '#3BA5FF'],
    ['🙋', 'Talk to a human', 'I want to talk to a human agent', '#FF9F1C'],
  ]

  return (
    <div className="app">
      <aside className="glass side">
        <div className="logo">✓ Checkr</div>
        <div className="profile"><i style={{ background: d.color }}>{user.name[0]}</i><div><b>{user.name}</b><small>{user.email}</small></div></div>
        <h3>Quick help</h3>
        {quick.map(([ic, label, msg, c]) => (
          <button key={label} className="quick" style={{ '--c': c }} onClick={() => send(msg)}><span>{ic}</span>{label}</button>
        ))}
        <button className="ghost" onClick={onLogout}>Switch customer</button>
      </aside>

      <main className="glass chat">
        <header><span className="dot" /> <b>Checkr</b><small>online · replies in seconds</small></header>
        <div className="feed" ref={feed}>
          {msgs.map((m, i) => (
            <div key={i} className={`row ${m.role}`}>
              <div className={`bubble ${m.error ? 'bad' : ''}`}>
                {fmt(m.text)}
                {m.escalated && <div className="note">🎫 A human agent has your ticket</div>}
                {m.steps?.length > 0 && <div className="used">{[...new Set(m.steps.map((s) => s.tool))].map((t) => <em key={t}>{TOOL[t]?.[0]} {TOOL[t]?.[1]}</em>)}</div>}
              </div>
            </div>
          ))}
          {busy && <div className="row bot"><div className="bubble typing"><i /><i /><i /></div></div>}
          {asking && !busy && (
            <div className="confirm">
              <button className="yes" onClick={() => send('Yes, go ahead')}>Yes, cancel it</button>
              <button className="no" onClick={() => send('No, keep it')}>No, keep it</button>
            </div>
          )}
        </div>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text) }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your message…" maxLength={1000} />
          <button disabled={busy || !text.trim()}>Send</button>
        </form>
      </main>

      <aside className="glass panel">
        <h3>Live agent activity</h3>
        <div className="stats">
          <div style={{ '--c': '#6C47FF' }}><b>{msgs.filter((m) => m.role === 'me').length}</b>messages</div>
          <div style={{ '--c': '#12C99B' }}><b>{calls}</b>tool calls</div>
          <div style={{ '--c': '#FF6B6B' }}><b>{tickets}</b>tickets</div>
        </div>
        <ul className="log">
          {activity.length === 0 && <li className="empty">Send a message and watch the tools Checkr uses appear here.</li>}
          {activity.map((a) => (
            <li key={a.id} className={a.status}>
              <span>{TOOL[a.tool]?.[0] || '🔧'}</span>
              <div><b>{TOOL[a.tool]?.[1] || a.tool}</b><small>{a.duration_ms} ms{a.attempts > 1 ? ` · ${a.attempts} tries` : ''}</small></div>
              <em>{STATUS[a.status] || a.status}</em>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
  return user ? <Chat user={user} onLogout={() => setUser(null)} /> : <Login onLogin={setUser} />
}
