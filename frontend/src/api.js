// Thin client for the FastAPI backend (proxied at /api by Vite).

async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new Error(formatError(data) || `${res.status} ${res.statusText}`)
  return data
}

// FastAPI errors: {detail: "msg"} or {detail: [{loc, msg}, ...]} for validation errors.
function formatError(data) {
  const d = data?.detail
  if (!d) return null
  if (typeof d === 'string') return d
  return d.map((e) => e.msg.replace(/^Value error, /, '')).join('; ')
}

function qs(params) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  stats: () => request('GET', '/stats'),
  rfqs: (params) => request('GET', `/rfqs${qs(params)}`),
  fscs: () => request('GET', '/fscs'),
  matches: (params) => request('GET', `/matches${qs(params)}`),
  getProfile: () => request('GET', '/profile'),
  putProfile: (profile) => request('PUT', '/profile', profile),
  setTriage: (sol, state) => request('PUT', `/triage/${encodeURIComponent(sol)}`, { state }),
  clearTriage: (sol) => request('DELETE', `/triage/${encodeURIComponent(sol)}`),
  refreshStatus: () => request('GET', '/refresh'),
  startRefresh: (body = {}) => request('POST', '/refresh', body),
}

// Append an NSN or FSC to the first capability group (creating it if needed).
export async function trackInProfile(kind, value) {
  const profile = await api.getProfile()
  const groups = profile.groups.length ? profile.groups : [{ supplier: null, nsns: [], fscs: [], keywords: [] }]
  const key = kind === 'nsn' ? 'nsns' : 'fscs'
  if (!groups[0][key].includes(value)) groups[0][key] = [...groups[0][key], value]
  return api.putProfile({ groups })
}
