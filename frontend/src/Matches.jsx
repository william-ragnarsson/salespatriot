import { useEffect, useState } from 'react'
import { api } from './api.js'
import { DibbsLink, ErrorBanner, NsnCell, Reasons, ReturnBy, StrengthBadge, TriageButtons } from './shared.jsx'

const VIEWS = [
  ['review', 'To review', (m) => !m.triage],
  ['interested', 'Interested', (m) => m.triage === 'interested'],
  ['dismissed', 'Dismissed', (m) => m.triage === 'dismissed'],
  ['all', 'All', () => true],
]

export default function Matches({ reloadKey, onGoProfile, onTriaged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [view, setView] = useState('review')
  const [openOnly, setOpenOnly] = useState(true)

  useEffect(() => {
    setError(null)
    api
      .matches({ include_dismissed: true, open_only: openOnly, limit: 1000 })
      .then(setData)
      .catch((e) => setError(e.message))
  }, [reloadKey, openOnly])

  function onTriage(sol, state) {
    setData((d) => ({
      ...d,
      items: d.items.map((m) => (m.solicitation_number === sol ? { ...m, triage: state } : m)),
    }))
    onTriaged?.()
  }

  if (error) return <ErrorBanner error={error} />
  if (!data) return <div className="loading">Loading matches…</div>

  if (data.profile_empty) {
    return (
      <div className="empty">
        <h2>Tell us what you can supply</h2>
        <p>
          Add the NSNs, FSCs and keywords you (or your suppliers) can quote on. We'll show only the RFQs that match,
          strongest first.
        </p>
        <button className="btn btn-primary" onClick={onGoProfile}>
          Set up your profile
        </button>
      </div>
    )
  }

  const filter = VIEWS.find((v) => v[0] === view)[2]
  const items = data.items.filter(filter)
  const counts = Object.fromEntries(VIEWS.map(([k, , f]) => [k, data.items.filter(f).length]))

  return (
    <div>
      <div className="toolbar">
        <div className="segmented">
          {VIEWS.map(([key, label]) => (
            <button key={key} className={view === key ? 'active' : ''} onClick={() => setView(key)}>
              {label} <span className="count">{counts[key]}</span>
            </button>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open RFQs only
        </label>
        <span className="spacer" />
        <span className="muted small">Ranked by match strength (NSN › FSC › keyword), then soonest return-by</span>
      </div>

      {items.length === 0 ? (
        <div className="empty">
          {view === 'review' && data.items.length > 0 ? (
            <>
              <h2>Inbox zero 🎉</h2>
              <p>Every match has been triaged. Check the Interested tab for the ones to quote.</p>
            </>
          ) : (
            <>
              <h2>No matches here</h2>
              <p>
                Nothing matches yet. Try broadening your profile with an FSC or keyword.{' '}
                <button className="btn btn-sm" onClick={onGoProfile}>
                  Edit profile
                </button>
              </p>
            </>
          )}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Match</th>
                <th>Why</th>
                <th>Nomenclature</th>
                <th>NSN</th>
                <th>Solicitation</th>
                <th className="num">Qty</th>
                <th>Return by</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr key={`${m.solicitation_number}|${m.pr_number}|${m.nsn}`} className={m.triage ? `row-${m.triage}` : ''}>
                  <td>
                    <StrengthBadge score={m.score} />
                  </td>
                  <td>
                    <Reasons reasons={m.reasons} />
                  </td>
                  <td className="nomen">
                    {m.nomenclature}
                    {m.status && m.status !== 'Open' && <span className="chip chip-urgent">{m.status}</span>}
                  </td>
                  <td>
                    <NsnCell rfq={m} />
                  </td>
                  <td className="mono small">{m.solicitation_number}</td>
                  <td className="num">{m.quantity?.toLocaleString() ?? '—'}</td>
                  <td>
                    <ReturnBy date={m.return_by} />
                  </td>
                  <td className="actions">
                    <TriageButtons rfq={m} onChange={onTriage} />
                    <DibbsLink rfq={m} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
