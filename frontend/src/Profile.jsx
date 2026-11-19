import { useEffect, useState } from 'react'
import { api } from './api.js'
import { ErrorBanner } from './shared.jsx'

const toText = (list) => list.join(', ')
const toList = (text) =>
  text
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)

const blank = () => ({ supplier: '', nsns: '', fscs: '', keywords: '' })

export default function Profile({ reloadKey, onSaved, onGoMatches }) {
  const [groups, setGroups] = useState(null)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .getProfile()
      .then((p) =>
        setGroups(
          p.groups.length
            ? p.groups.map((g) => ({
                supplier: g.supplier || '',
                nsns: toText(g.nsns),
                fscs: toText(g.fscs),
                keywords: toText(g.keywords),
              }))
            : [blank()],
        ),
      )
      .catch((e) => setError(e.message))
  }, [reloadKey])

  function update(i, field, value) {
    setSaved(null)
    setGroups((gs) => gs.map((g, j) => (j === i ? { ...g, [field]: value } : g)))
  }

  async function save() {
    setSaving(true)
    setError(null)
    setSaved(null)
    try {
      const payload = {
        groups: groups
          .map((g) => ({
            supplier: g.supplier.trim() || null,
            nsns: toList(g.nsns),
            fscs: toList(g.fscs),
            keywords: toList(g.keywords),
          }))
          .filter((g) => g.supplier || g.nsns.length || g.fscs.length || g.keywords.length),
      }
      await api.putProfile(payload)
      const m = await api.matches({ limit: 1 })
      setSaved(m.total)
      onSaved?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!groups) return error ? <ErrorBanner error={error} /> : <div className="loading">Loading profile…</div>

  return (
    <div className="profile">
      <p className="intro">
        Tell us once what you can supply, and <strong>My matches</strong> shows only the RFQs worth quoting.{' '}
        <strong>Manufacturers</strong>: one group with what you make. <strong>Distributors</strong>: one group per
        supplier, so each match tells you who to call.
      </p>

      <div className="legend">
        <span>
          <span className="badge badge-nsn">NSN</span> exact part you supply (strongest)
        </span>
        <span>
          <span className="badge badge-fsc">FSC</span> 4-digit class, e.g. <code>5305</code> = screws
        </span>
        <span>
          <span className="badge badge-kw">Keyword</span> appears in the nomenclature, e.g. <code>bolt</code>
        </span>
      </div>

      {groups.map((g, i) => (
        <div className="card" key={i}>
          <div className="card-head">
            <input
              className="supplier"
              placeholder="Supplier name (leave blank if you make it yourself)"
              value={g.supplier}
              onChange={(e) => update(i, 'supplier', e.target.value)}
            />
            {groups.length > 1 && (
              <button className="btn btn-sm" onClick={() => setGroups((gs) => gs.filter((_, j) => j !== i))}>
                Remove
              </button>
            )}
          </div>
          <div className="fields">
            <label>
              <span>NSNs</span>
              <textarea
                rows={3}
                placeholder="8455-01-469-8015, 5305-00-123-4567"
                value={g.nsns}
                onChange={(e) => update(i, 'nsns', e.target.value)}
              />
            </label>
            <label>
              <span>FSCs</span>
              <textarea rows={3} placeholder="5305, 8455" value={g.fscs} onChange={(e) => update(i, 'fscs', e.target.value)} />
            </label>
            <label>
              <span>Keywords</span>
              <textarea
                rows={3}
                placeholder="screw, bolt, insignia"
                value={g.keywords}
                onChange={(e) => update(i, 'keywords', e.target.value)}
              />
            </label>
          </div>
        </div>
      ))}

      <div className="toolbar">
        <button className="btn" onClick={() => setGroups((gs) => [...gs, blank()])}>
          + Add supplier group
        </button>
        <span className="spacer" />
        {saved !== null && (
          <span className="saved">
            ✓ Saved: {saved} matching RFQ{saved === 1 ? '' : 's'}{' '}
            <button className="btn btn-sm" onClick={onGoMatches}>
              View matches →
            </button>
          </span>
        )}
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save profile'}
        </button>
      </div>
      <ErrorBanner error={error} />
    </div>
  )
}
