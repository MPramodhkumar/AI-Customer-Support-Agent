import { useEffect, useRef, useState } from 'react'
import { chat, me, login as loginAccount, register, demoAccount, orders as getOrders, createOrder, markDelivered } from './api'
import './styles.css'

const TOOL = { list_my_orders: ['≡', 'Order history'], get_order_status: ['📦', 'Order lookup'], cancel_order: ['✂️', 'Cancel order'], check_refund_status: ['💸', 'Refund check'], create_support_ticket: ['🎫', 'Support ticket'], search_knowledge_base: ['📚', 'Help center'] }
const STATUS = { success: 'Done', failed: 'Failed', needs_confirmation: 'Needs your OK', blocked: 'Blocked', skipped: 'Skipped' }
const fmt = (t) => t.split(/(\*\*[^*]+\*\*)/g).map((p, i) => p.startsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p)

function ThemeButton({ theme, onToggle }) {
  const next = theme === 'light' ? 'dark' : 'light'
  return <button className="theme-toggle" onClick={onToggle} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}><span aria-hidden="true">{theme === 'light' ? '☾' : '☀'}</span>{next} mode</button>
}

function Login({ onLogin, theme, onToggleTheme }) {
  const [key, setKey] = useState(''), [email, setEmail] = useState(''), [password, setPassword] = useState(''), [name, setName] = useState('')
  const [creating, setCreating] = useState(false), [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  function finish(profile) {
    onLogin({ ...profile, key: profile.key || profile.api_key, isDemo: Boolean(profile.is_demo), demo: { color: '#6C47FF' } })
  }
  async function startDemo() {
    setBusy(true); setErr('')
    try { finish(await demoAccount()) } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  async function go(k) {
    setBusy(true); setErr('')
    try { finish({ key: k, ...await me(k) }) } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  async function submitAccount(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try { finish(await (creating ? register({ name, email, password }) : loginAccount({ email, password }))) }
    catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return <main className="login">
    <ThemeButton theme={theme} onToggle={onToggleTheme}/>
    <section className="hero">
      <div className="logo login-logo">checkr</div>
      <div className="hero-kicker"><span className="hero-kicker-dot"/> CUSTOMER CARE, MADE SIMPLE</div>
      <h1>Your orders.<br/>Handled.</h1>
      <p>Track a delivery, sort out a refund, or get help from Checkr. Everything you need is in one friendly place.</p>
      <div className="hero-preview">
        <div className="preview-top"><span className="preview-icon">BOX</span><span><b>Order support</b><small>All your orders, in one place</small></span><span className="preview-check">OK</span></div>
        <div className="preview-line"><i/><span>Track deliveries</span><b>Ready</b></div>
        <div className="preview-line"><i/><span>Manage order details</span><b>Ready</b></div>
        <div className="preview-line"><i/><span>Chat with Checkr</span><b>Online</b></div>
      </div>
      <div className="hero-footnote"><span>Secure account access</span><span>Personalized support</span></div>
    </section>
    <section className="glass login-card">
      <button className="demo-entry" disabled={busy} onClick={startDemo}><span className="demo-entry-icon" aria-hidden="true">✦</span><span><b>{busy ? 'Opening demo…' : 'Click here: Robert’s agent'}</b><small>Explore the support chat without signing in</small></span><span className="demo-entry-arrow" aria-hidden="true">→</span></button>
      <div className="login-heading"><span>{creating ? 'GET STARTED' : 'WELCOME BACK'}</span><h2>{creating ? 'Create your account' : 'Sign in to Checkr'}</h2><p>{creating ? 'A better way to keep up with every order.' : 'Your orders and support are ready.'}</p></div>
      <form className="account-form" onSubmit={submitAccount}>
        {creating && <label>Your name<input required maxLength={100} autoComplete="name" placeholder="e.g. Alex Morgan" value={name} onChange={(e) => setName(e.target.value)} /></label>}
        <label>Email address<input required type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label>Password<input required type="password" autoComplete={creating ? 'new-password' : 'current-password'} minLength={creating ? 8 : 1} placeholder={creating ? 'At least 8 characters' : 'Enter your password'} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {err && <p className="err" role="alert">{err}</p>}
        <button className="login-submit" disabled={busy}>{busy ? 'Please wait…' : creating ? 'Create account' : 'Sign in'}</button>
        <p className="account-switch">{creating ? 'Already have an account?' : 'New to Checkr?'} <button type="button" className="text-button" onClick={() => { setCreating(!creating); setErr('') }}>{creating ? 'Sign in' : 'Create an account'}</button></p>
      </form>
      <details className="api-login"><summary>Sign in with an API key</summary><form onSubmit={(e) => { e.preventDefault(); key && go(key) }}><input aria-label="API key" placeholder="Paste your API key" value={key} onChange={(e) => setKey(e.target.value)} /><button disabled={busy}>Continue</button></form></details>
      <div className="login-security"><span className="security-dot"/> Your account is protected</div>
    </section>
  </main>
}

function Chat({ user, onLogout, theme, onToggleTheme }) {
  const [sessionId] = useState(() => crypto.randomUUID()), [msgs, setMsgs] = useState([{ role: 'bot', text: `Hi ${user.name.split(' ')[0]}! I'm Checkr. What can I sort out for you today?` }])
  const [activity, setActivity] = useState([]), [busy, setBusy] = useState(false), [text, setText] = useState(''), [myOrders, setMyOrders] = useState([])
  const [showOrder, setShowOrder] = useState(false), [showHistory, setShowHistory] = useState(false), [orderItem, setOrderItem] = useState(''), [orderPrice, setOrderPrice] = useState(''), [orderError, setOrderError] = useState(''), [orderBusy, setOrderBusy] = useState(false), [historyError, setHistoryError] = useState('')
  const feed = useRef(null)
  useEffect(() => { getOrders(user.key).then(setMyOrders).catch(() => {}) }, [user.key])
  useEffect(() => { const f = feed.current; if (f) f.scrollTo({ top: f.scrollHeight, behavior: 'smooth' }) }, [msgs, busy])
  async function send(message) {
    message = message.trim(); if (!message || busy) return
    setText(''); setBusy(true); setMsgs((m) => [...m, { role: 'me', text: message }])
    try { const r = await chat(user.key, sessionId, message); setMsgs((m) => [...m, { role: 'bot', text: r.reply, steps: r.steps, escalated: r.escalated, orders: r.orders }]); setActivity((a) => [...r.steps.map((s, i) => ({ ...s, id: `${Date.now()}-${i}` })).reverse(), ...a]) }
    catch (e) { setMsgs((m) => [...m, { role: 'bot', text: e.message, error: true }]) }
    setBusy(false)
  }
  async function placeOrder(e) {
    e.preventDefault(); setOrderBusy(true); setOrderError('')
    try { const created = await createOrder(user.key, { item: orderItem, price: Number(orderPrice) }); setMyOrders((all) => [created, ...all]); setOrderItem(''); setOrderPrice(''); setShowOrder(false); send(`Where is my order ${created.id}?`) }
    catch (e) { setOrderError(e.message) }
    setOrderBusy(false)
  }
  async function deliverOrder(id) {
    setHistoryError('')
    try { const updated = await markDelivered(user.key, id); setMyOrders((all) => all.map((order) => order.id === id ? updated : order)) }
    catch (e) { setHistoryError(e.message) }
  }
  async function deliverFromChat(id) {
    try {
      const updated = await markDelivered(user.key, id)
      const asOrder = { order_id: updated.id, item: updated.item, price: updated.price, status: updated.status, expected_delivery: null }
      setMyOrders((all) => all.map((order) => order.id === id ? updated : order))
      setMsgs((all) => [...all.map((message) => message.orders ? { ...message, orders: message.orders.map((order) => order.order_id === id ? asOrder : order) } : message), { role: 'bot', text: `Order #${id} is now marked as delivered.` }])
    } catch (e) { setMsgs((all) => [...all, { role: 'bot', text: e.message, error: true }]) }
  }
  const last = msgs[msgs.length - 1], asking = last.role === 'bot' && last.steps?.find((s) => s.status === 'needs_confirmation')
  const calls = activity.filter((a) => a.status !== 'skipped').length, tickets = activity.filter((a) => a.tool === 'create_support_ticket' && a.status === 'success').length, latest = myOrders[0]
  const quick = [['📦', 'Track my order', latest ? `Where is my order ${latest.id}?` : 'Where is my order?', '#6C47FF'], ['✂️', 'Cancel an order', latest ? `I want to cancel order ${latest.id}` : 'I want to cancel an order', '#FF6B6B'], ['💸', 'Refund status', latest ? `What\'s the refund status for order ${latest.id}?` : 'Check my refund status', '#12C99B'], ['📚', 'Return policy', 'What is your return policy?', '#3BA5FF'], ['🙋', 'Talk to a human', 'I want to talk to a human agent', '#FF9F1C']]
  return <div className="app">
    <ThemeButton theme={theme} onToggle={onToggleTheme}/>
    <aside className="glass side"><div className="logo">✓ Checkr</div><div className="profile"><i style={{ background: user.demo.color }}>{user.name[0]}</i><div><b>{user.isDemo ? 'Robert’s agent demo' : user.name}</b><small>{user.isDemo ? 'Demo mode · sample orders' : user.email}</small></div></div>
      <button className="order-spotlight" onClick={() => { setOrderError(''); setShowOrder(true) }}><span className="order-spotlight-icon">＋</span><span className="order-spotlight-copy"><b>Place an Order</b><small>Find something you’ll love</small></span></button>
      <h3>Quick help</h3>
      {quick.map(([ic, label, msg, c]) => <button key={label} className="quick" style={{ '--c': c }} onClick={() => send(msg)}><span>{ic}</span>{label}</button>)}
      <button className="quick history-button" onClick={() => { setHistoryError(''); setShowHistory(true) }}><span>▤</span>Order Details</button>
      {latest && <small className="latest-order">Latest: #{latest.id} · {latest.item} ({latest.status})</small>}<button className="ghost" onClick={onLogout}>Logout</button>
    </aside>
    {showOrder && <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowOrder(false) }}><form className="glass order-modal" onSubmit={placeOrder}><button type="button" className="modal-close" onClick={() => setShowOrder(false)}>×</button><h2>Place an order</h2><p>Order as {user.name}</p><label>Item name<input required maxLength={200} placeholder="e.g. Ceramic travel mug" value={orderItem} onChange={(e) => setOrderItem(e.target.value)} /></label><label>Price<input required type="number" min="0.01" max="1000000" step="0.01" placeholder="0.00" value={orderPrice} onChange={(e) => setOrderPrice(e.target.value)} /></label>{orderError && <p className="err">{orderError}</p>}<button className="place-submit" disabled={orderBusy}>{orderBusy ? 'Placing…' : 'Place order'}</button></form></div>}
    {showHistory && <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowHistory(false) }}><section className="glass history-modal"><button type="button" className="modal-close" onClick={() => setShowHistory(false)}>×</button><h2>Order Details</h2><p>Your order history</p>{historyError && <p className="err">{historyError}</p>}{myOrders.length === 0 ? <p className="history-empty">No orders yet. Place an order to get started.</p> : <ul className="order-list">{myOrders.map((order) => <li key={order.id}><div><b>#{order.id} · {order.item}</b><small>₹{Number(order.price).toFixed(2)}</small></div><span className={`order-status ${order.status}`}>{order.status}</span>{order.status !== 'delivered' && order.status !== 'cancelled' && <button onClick={() => deliverOrder(order.id)}>Mark delivered</button>}</li>)}</ul>}</section></div>}
    <main className="glass chat"><header><span className="dot"/><b>Checkr</b><small>online · replies in seconds</small></header><div className="feed" ref={feed}>
      {msgs.map((m, i) => <div key={i} className={`row ${m.role}`}><div className={`bubble ${m.error ? 'bad' : ''}`}>{fmt(m.text)}{i === 0 && m.role === 'bot' && <div className="chat-suggestions"><button onClick={() => send('List all my orders')}>List my orders</button><button onClick={() => { setOrderError(''); setShowOrder(true) }}>Place an order</button></div>}{m.escalated && <div className="note">🎫 A human agent has your ticket</div>}{m.steps?.length > 0 && <div className="used">{[...new Set(m.steps.map((s) => s.tool))].map((t) => <em key={t}>{TOOL[t]?.[0]} {TOOL[t]?.[1]}</em>)}</div>}{m.orders?.length > 0 && <div className="chat-order-list">{m.orders.map((order) => <article className="chat-order" key={order.order_id}><div className="chat-order-heading"><span className="chat-order-icon">📦</span><div><b>{order.item}</b><small>Order #{order.order_id} · ₹{Number(order.price).toFixed(2)}</small></div><span className={`order-status ${order.status}`}>{order.status}</span></div><div className="chat-order-actions"><button onClick={() => send(`Track order ${order.order_id}`)}>Track</button><button onClick={() => send(`Check refund status for order ${order.order_id}`)}>Refund</button>{order.status !== 'delivered' && order.status !== 'cancelled' && <button onClick={() => send(`I want to cancel order ${order.order_id}`)}>Cancel</button>}{order.status !== 'delivered' && order.status !== 'cancelled' && <button onClick={() => deliverFromChat(order.order_id)}>Mark delivered</button>}</div></article>)}</div>}{m.steps?.some((step) => step.tool === 'list_my_orders') && <button className="chat-place-order" onClick={() => { setOrderError(''); setShowOrder(true) }}>＋ Place another order</button>}</div></div>)}
      {busy && <div className="row bot"><div className="bubble typing"><i/><i/><i/></div></div>}{asking && !busy && <div className="confirm"><button className="yes" onClick={() => send('Yes, go ahead')}>Yes, cancel it</button><button className="no" onClick={() => send('No, keep it')}>No, keep it</button></div>}
    </div><form className="composer" onSubmit={(e) => { e.preventDefault(); send(text) }}><input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your message…" maxLength={1000}/><button disabled={busy || !text.trim()}>Send</button></form></main>
    <aside className="glass panel"><h3>Live agent activity</h3><div className="stats"><div style={{ '--c': '#6C47FF' }}><b>{msgs.filter((m) => m.role === 'me').length}</b>messages</div><div style={{ '--c': '#12C99B' }}><b>{calls}</b>tool calls</div><div style={{ '--c': '#FF6B6B' }}><b>{tickets}</b>tickets</div></div><ul className="log">{activity.length === 0 && <li className="empty">Send a message and watch the tools Checkr uses appear here.</li>}{activity.map((a) => <li key={a.id} className={a.status}><span>{TOOL[a.tool]?.[0] || '🔧'}</span><div><b>{TOOL[a.tool]?.[1] || a.tool}</b><small>{a.duration_ms} ms{a.attempts > 1 ? ` · ${a.attempts} tries` : ''}</small></div><em>{STATUS[a.status] || a.status}</em></li>)}</ul></aside>
  </div>
}

export default function App() {
  const [user, setUser] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('checkr-theme') || 'light')
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('checkr-theme', theme) }, [theme])
  const toggleTheme = () => setTheme((current) => current === 'light' ? 'dark' : 'light')
  return user ? <Chat user={user} onLogout={() => setUser(null)} theme={theme} onToggleTheme={toggleTheme}/> : <Login onLogin={setUser} theme={theme} onToggleTheme={toggleTheme}/>
}
