import { useState } from 'react'
import { api } from './api.js'

export function DibbsLink({ rfq }) {
  return (
    <a className="btn btn-link" href={rfq.dibbs_url} target="_blank" rel="noreferrer" title="Open the solicitation package on DIBBS">
      Open on DIBBS ↗
    </a>
  )
}

export function NsnCell({ rfq }) {
  return rfq.nsn_url ? (
    <a className="mono" href={rfq.nsn_url} target="_blank" rel="noreferrer" title="All open RFQs for this NSN on DIBBS">
      {rfq.nsn_display}
    </a>
  ) : (
    <span className="mono">{rfq.nsn_display}</span>
  )
}

function daysUntil(iso) {
  if (!iso) return null
  const [y, m, d] = iso.split('-').map(Number)
  const today = new Date()
  const t0 = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((Date.UTC(y, m - 1, d) - t0) / 86400000)
}

export function ReturnBy({ date }) {
  const n = daysUntil(date)
  if (n === null) return <span className="muted">—</span>
  const label = n < 0 ? 'closed' : n === 0 ? 'today' : `in ${n}d`
  const cls = n <= 2 ? 'chip chip-urgent' : n <= 5 ? 'chip chip-soon' : 'chip'
  return (
    <span className="nowrap">
      {date.slice(5)} <span className={cls}>{label}</span>
    </span>
  )
}

export function TriageButtons({ rfq, onChange }) {
  const [busy, setBusy] = useState(false)
  const state = rfq.triage

  async function set(next) {
    setBusy(true)
    try {
      if (next) await api.setTriage(rfq.solicitation_number, next)
      else await api.clearTriage(rfq.solicitation_number)
      onChange?.(rfq.solicitation_number, next)
    } catch (e) {
      alert(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="triage nowrap">
      <button
        className={`btn btn-sm ${state === 'interested' ? 'btn-interested' : ''}`}
        disabled={busy}
        onClick={() => set(state === 'interested' ? null : 'interested')}
        title={state === 'interested' ? 'Remove from interested' : 'Mark as interested'}
      >
        ★ {state === 'interested' ? 'Interested' : 'Interest'}
      </button>
      <button
        className={`btn btn-sm ${state === 'dismissed' ? 'btn-dismissed' : ''}`}
        disabled={busy}
        onClick={() => set(state === 'dismissed' ? null : 'dismissed')}
        title={state === 'dismissed' ? 'Undo dismiss' : 'Not for us: hide from matches'}
      >
        {state === 'dismissed' ? '↺ Undo' : '✕ Dismiss'}
      </button>
    </span>
  )
}

const STRENGTH = { 3: ['NSN', 'badge-nsn'], 2: ['FSC', 'badge-fsc'], 1: ['Keyword', 'badge-kw'] }

export function StrengthBadge({ score }) {
  const [label, cls] = STRENGTH[score] || ['?', '']
  return <span className={`badge ${cls}`}>{label}</span>
}

export function Reasons({ reasons }) {
  return (
    <span className="reasons">
      {reasons.map((r, i) => (
        <span key={i} className={`reason reason-${r.kind}`}>
          {r.kind === 'keyword' ? `“${r.value}”` : `${r.kind.toUpperCase()} ${r.value}`}
          {r.supplier && <span className="reason-supplier"> · {r.supplier}</span>}
        </span>
      ))}
    </span>
  )
}

export function Pager({ total, limit, offset, onChange }) {
  if (total <= limit) return null
  const page = Math.floor(offset / limit) + 1
  const pages = Math.ceil(total / limit)
  return (
    <div className="pager">
      <button className="btn btn-sm" disabled={page <= 1} onClick={() => onChange(offset - limit)}>
        ← Prev
      </button>
      <span className="muted">
        Page {page} of {pages}
      </span>
      <button className="btn btn-sm" disabled={page >= pages} onClick={() => onChange(offset + limit)}>
        Next →
      </button>
    </div>
  )
}

export function ErrorBanner({ error }) {
  if (!error) return null
  return <div className="error">⚠ {error}</div>
}
