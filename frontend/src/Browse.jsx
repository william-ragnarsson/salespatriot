import { useEffect, useState } from 'react'
import { api, trackInProfile } from './api.js'
import { DibbsLink, ErrorBanner, NsnCell, Pager, ReturnBy, TriageButtons } from './shared.jsx'

const LIMIT = 50
const COLUMNS = [
  ['nomenclature', 'Nomenclature'],
  ['nsn', 'NSN'],
  ['fsc', 'FSC'],
  ['solicitation_number', 'Solicitation'],
  ['quantity', 'Qty', 'num'],
  ['issue_date', 'Issued'],
  ['return_by', 'Return by'],
]

export default function Browse({ reloadKey, onTriaged, onProfileChanged }) {
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [fsc, setFsc] = useState('')
  const [status, setStatus] = useState('')
  const [triage, setTriage] = useState('')
  const [sort, setSort] = useState('return_by')
  const [order, setOrder] = useState('asc')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState(null)
  const [fscs, setFscs] = useState([])
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])

  // Any filter change goes back to page 1.
  useEffect(() => setOffset(0), [debouncedQ, fsc, status, triage, sort, order])

  useEffect(() => {
    api.fscs().then(setFscs).catch(() => {})
  }, [reloadKey])

  useEffect(() => {
    let stale = false // ignore responses for filters that have since changed
    setError(null)
    api
      .rfqs({ q: debouncedQ, fsc, status, triage, sort, order, limit: LIMIT, offset })
      .then((d) => !stale && setData(d))
      .catch((e) => !stale && setError(e.message))
    return () => {
      stale = true
    }
  }, [debouncedQ, fsc, status, triage, sort, order, offset, reloadKey])

  function toggleSort(col) {
    if (col === sort) setOrder(order === 'asc' ? 'desc' : 'asc')
    else {
      setSort(col)
      setOrder(col === 'quantity' ? 'desc' : 'asc')
    }
  }

  function onTriage(sol, state) {
    setData((d) => ({
      ...d,
      items: d.items.map((r) => (r.solicitation_number === sol ? { ...r, triage: state } : r)),
    }))
    onTriaged?.()
  }

  async function track(kind, value, label) {
    try {
      await trackInProfile(kind, value)
      setToast(`Added ${label} to your profile`)
      onProfileChanged?.()
    } catch (e) {
      setToast(`Could not update profile: ${e.message}`)
    }
    setTimeout(() => setToast(null), 2500)
  }

  const filtersActive = q || fsc || status || triage

  return (
    <div>
      <div className="toolbar">
        <input
          className="search"
          type="search"
          placeholder="Search nomenclature, NSN, solicitation # or PR #…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <select value={fsc} onChange={(e) => setFsc(e.target.value)}>
          <option value="">All FSCs</option>
          {fscs.map((f) => (
            <option key={f.fsc} value={f.fsc}>
              {f.fsc} ({f.count})
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          <option value="Open">Open</option>
          <option value="Removed">Removed</option>
        </select>
        <select value={triage} onChange={(e) => setTriage(e.target.value)}>
          <option value="">Any triage</option>
          <option value="untriaged">Not triaged</option>
          <option value="interested">Interested</option>
          <option value="dismissed">Dismissed</option>
        </select>
        {filtersActive && (
          <button
            className="btn btn-sm"
            onClick={() => {
              setQ('')
              setFsc('')
              setStatus('')
              setTriage('')
            }}
          >
            Clear
          </button>
        )}
        <span className="spacer" />
        {data && <span className="muted">{data.total.toLocaleString()} RFQs</span>}
      </div>

      {toast && <div className="toast">{toast}</div>}
      <ErrorBanner error={error} />

      {data && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {COLUMNS.map(([key, label, cls]) => (
                    <th key={key} className={`sortable ${cls || ''}`} onClick={() => toggleSort(key)}>
                      {label}
                      {sort === key && <span className="sort-arrow">{order === 'asc' ? ' ▲' : ' ▼'}</span>}
                    </th>
                  ))}
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={COLUMNS.length + 2} className="empty-row">
                      No RFQs match these filters.
                    </td>
                  </tr>
                )}
                {data.items.map((r) => (
                  <tr key={`${r.solicitation_number}|${r.pr_number}|${r.nsn}`} className={r.triage ? `row-${r.triage}` : ''}>
                    <td className="nomen">{r.nomenclature}</td>
                    <td className="nowrap">
                      <NsnCell rfq={r} />
                      <button className="link-btn" title="Track this exact NSN in your profile" onClick={() => track('nsn', r.nsn, `NSN ${r.nsn_display}`)}>
                        + track
                      </button>
                    </td>
                    <td className="nowrap">
                      <button className="fsc-btn" title="Filter by this FSC" onClick={() => setFsc(r.fsc)}>
                        {r.fsc}
                      </button>
                      <button className="link-btn" title="Track this whole FSC in your profile" onClick={() => track('fsc', r.fsc, `FSC ${r.fsc}`)}>
                        + track
                      </button>
                    </td>
                    <td className="mono small">{r.solicitation_number}</td>
                    <td className="num">{r.quantity?.toLocaleString() ?? '—'}</td>
                    <td className="small nowrap">{r.issue_date}</td>
                    <td>
                      <ReturnBy date={r.return_by} />
                    </td>
                    <td>
                      <span className={`chip ${r.status === 'Open' ? 'chip-open' : 'chip-urgent'}`}>{r.status || '—'}</span>
                    </td>
                    <td className="actions">
                      <TriageButtons rfq={r} onChange={onTriage} />
                      <DibbsLink rfq={r} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </div>
  )
}
