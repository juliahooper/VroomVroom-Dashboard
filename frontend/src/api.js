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

/**
 * Fetch historic snapshots with full metrics for charts.
 * @param {string} [device='pc-01']
 * @param {number} [limit=100]
 * @returns {Promise<Array<{ id: number, device_id: string, timestamp_utc: string, metrics: Array<{ name: string, unit: string, value: number, status: string }> }>>}
 */
export async function fetchHistoricSnapshots(device = 'pc-01', limit = 100) {
  const params = new URLSearchParams({ device, limit: String(limit), expand: 'metrics' })
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
