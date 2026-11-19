import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Browse from './Browse.jsx'
import Matches from './Matches.jsx'
import Profile from './Profile.jsx'

const TABS = [
  ['matches', 'My matches'],
  ['browse', 'All RFQs'],
  ['profile', 'Profile'],
]

export default function App() {
  const [tab, setTab] = useState('matches')
  const [reloadKey, setReloadKey] = useState(0) // bump to make every view refetch
  const [stats, setStats] = useState(null)
  const [matchCount, setMatchCount] = useState(null)
  const [refresh, setRefresh] = useState(null)
  const [apiDown, setApiDown] = useState(false)
  const pollRef = useRef(null)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  const loadStats = useCallback(() => {
    api
      .stats()
      .then((s) => {
        setStats(s)
        setApiDown(false)
      })
      .catch(() => setApiDown(true))
    api
      .matches({ limit: 1 })
      .then((m) => setMatchCount(m.profile_empty ? null : m.total))
      .catch(() => {})
  }, [])

  useEffect(loadStats, [loadStats, reloadKey])

  function switchTab(key) {
    setTab(key)
    reload() // views stay mounted (keeping their filters) but refetch fresh data
  }

  async function startRefresh(body) {
    try {
      setRefresh(await api.startRefresh(body))
    } catch (e) {
      setRefresh({ running: false, error: e.message })
      return
    }
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.refreshStatus()
        setRefresh(s)
        if (!s.running) {
          clearInterval(pollRef.current)
          reload()
        }
      } catch (e) {
        clearInterval(pollRef.current)
        setRefresh({ running: false, error: e.message })
      }
    }, 1500)
  }

  useEffect(() => () => clearInterval(pollRef.current), [])

  return (
    <div className="app">
      <header>
        <div className="brand">
          <div className="logo">◆</div>
          <div>
            <h1>DIBBS Opportunities</h1>
            <div className="subtitle">Today's DLA RFQs, filtered to what you can supply</div>
          </div>
        </div>
        <div className="header-right">
          {stats && (
            <div className="stats">
              <Stat label="RFQs" value={stats.total} />
              <Stat label="Open" value={stats.open} />
              <Stat label="Interested" value={stats.triage.interested} />
              <Stat label="Dismissed" value={stats.triage.dismissed} />
              <div className="stat">
                <div className="stat-label">Issued</div>
                <div className="stat-value small">{stats.issue_dates[0]?.issue_date || '—'}</div>
              </div>
            </div>
          )}
          <RefreshControl refresh={refresh} stats={stats} onStart={startRefresh} />
        </div>
      </header>

      <nav className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => switchTab(key)}>
            {label}
            {key === 'matches' && matchCount !== null && <span className="count">{matchCount}</span>}
          </button>
        ))}
      </nav>

      <main>
        {apiDown && (
          <div className="error">
            ⚠ Can't reach the API. Start it with <code>.venv/bin/uvicorn api:app --reload --port 8000</code>
          </div>
        )}
        <section hidden={tab !== 'matches'}>
          <Matches reloadKey={reloadKey} onGoProfile={() => switchTab('profile')} onTriaged={loadStats} />
        </section>
        <section hidden={tab !== 'browse'}>
          <Browse reloadKey={reloadKey} onTriaged={loadStats} onProfileChanged={loadStats} />
        </section>
        <section hidden={tab !== 'profile'}>
          <Profile reloadKey={reloadKey} onSaved={loadStats} onGoMatches={() => switchTab('matches')} />
        </section>
      </main>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value.toLocaleString()}</div>
    </div>
  )
}

function RefreshControl({ refresh, stats, onStart }) {
  const running = refresh?.running
  let status = null
  if (running) status = `Scraping… page ${refresh.pages + 1} · ${refresh.rows} rows`
  else if (refresh?.error) status = `Refresh failed: ${refresh.error}`
  else if (refresh?.finished_at) status = `✓ ${refresh.rows} rows (${refresh.inserted} new)`
  else if (stats?.last_scraped_at) status = `Last scraped ${new Date(stats.last_scraped_at).toLocaleString()}`

  return (
    <div className="refresh">
      <button className="btn btn-primary" disabled={running} onClick={() => onStart({})}>
        {running ? 'Refreshing…' : '↻ Refresh from DIBBS'}
      </button>
      {status && <div className={`refresh-status ${refresh?.error ? 'is-error' : ''}`}>{status}</div>}
      {refresh?.error && !running && (
        <button className="link-btn" onClick={() => onStart({ from_file: 'samples/page1.html' })}>
          Load saved sample page instead
        </button>
      )}
    </div>
  )
}
