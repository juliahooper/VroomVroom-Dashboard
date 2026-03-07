const API_BASE = '' // proxied in dev, same origin in prod

/**
 * Fetch latest snapshot with full metrics for a device (live view).
 * @param {string} [device='pc-01']
 * @returns {Promise<{ id: number, device_id: string, timestamp_utc: string, metrics: Array<{ name: string, unit: string, value: number, status: string }> }>}
 */
export async function fetchLatestSnapshot(device = 'pc-01') {
  const res = await fetch(`${API_BASE}/orm/snapshots/latest?device=${encodeURIComponent(device)}`)
  if (!res.ok) {
    if (res.status === 404) return null
    throw new Error(`Latest snapshot: ${res.status}`)
  }
  return res.json()
}

/** ISO 8601 timestamp for 7 days ago (or since first data if less). */
export function getHistoricSinceIso() {
  const d = new Date()
  d.setDate(d.getDate() - 7)
  return d.toISOString()
}

/**
 * Fetch historic snapshots with full metrics for charts.
 * @param {string} [device='pc-01']
 * @param {number} [limit=100]
 * @param {string} [since] ISO 8601 timestamp; if omitted, uses 7 days ago (last week)
 * @returns {Promise<Array<{ id: number, device_id: string, timestamp_utc: string, metrics: Array<{ name: string, unit: string, value: number, status: string }> }>>}
 */
export async function fetchHistoricSnapshots(device = 'pc-01', limit = 100, since = getHistoricSinceIso()) {
  const params = new URLSearchParams({ device, limit: String(limit), expand: 'metrics' })
  if (since) params.set('since', since)
  const res = await fetch(`${API_BASE}/orm/snapshots?${params}`)
  if (!res.ok) throw new Error(`Historic snapshots: ${res.status}`)
  const data = await res.json()
  return Array.isArray(data) ? data.reverse() : [] // chronological for charts
}

/**
 * Fetch danger thresholds (and warning_fraction) for gauge green/yellow/red zones.
 * @returns {Promise<{ thread_count: number, ram_percent: number, disk_usage_percent: number, warning_fraction: number }>}
 */
export async function fetchThresholds() {
  const res = await fetch(`${API_BASE}/orm/thresholds`)
  if (!res.ok) throw new Error(`Thresholds: ${res.status}`)
  return res.json()
}

/**
 * Fetch locations (id, name, county, lat, lng, cold_water_shock_risk_score, alert_count).
 * Locations are seeded in backend; metrics come from latest snapshot per mobile:loc_xxx.
 */
export async function fetchLocations() {
  const res = await fetch(`${API_BASE}/orm/locations`)
  if (!res.ok) {
    if (res.status === 404) return []
    throw new Error(`Locations: ${res.status}`)
  }
  const data = await res.json()
  return Array.isArray(data) ? data : []
}

export function getMetric(metrics, name) {
  return metrics?.find((m) => m.name === name)
}

/**
 * Create a command for a device (stretch goal). E.g. play_alert opens YouTube on the PC.
 * @param {string} deviceId - e.g. 'pc-01'
 * @param {string} command - e.g. 'play_alert'
 */
export async function sendCommand(deviceId, command = 'play_alert') {
  const res = await fetch(`${API_BASE}/orm/commands`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id: deviceId, command }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || `Send command: ${res.status}`)
  }
  return res.json()
}
