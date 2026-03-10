/**
 * Device and metric constants. IDs match PostgreSQL/Firebase.
 * Location ids (loc_lough_*) map to device_id = mobile:loc_xxx for metrics.
 */
export const DEVICE_PC = 'pc-01'
export const DEVICE_YOUTUBE = 'youtube-vroom-vroom'
export const DEVICE_PREFIX_MOBILE = 'mobile:'

export const deviceIdForLocation = (locationId) =>
  locationId ? `${DEVICE_PREFIX_MOBILE}${locationId}` : null

/** PC metrics (gauges) */
export const METRIC_THREADS = 'Running Threads'
export const METRIC_DISK = 'Disk Usage'
export const METRIC_RAM = 'RAM Usage'

/** YouTube metrics */
export const METRIC_TOTAL_STREAMS = 'total_streams'
export const METRIC_LIKE_COUNT = 'Like Count'

/** Location metrics (from mobile snapshots) */
export const METRIC_COLD_WATER_SHOCK = 'Cold Water Shock Risk'
export const METRIC_ALERT_COUNT = 'Alert Count'
export const METRIC_WATER_TEMP = 'Water Temp'

export const PC_METRIC_KEYS = [
  { key: METRIC_THREADS, color: '#0a4d7a', name: 'Threads' },
  { key: METRIC_DISK, color: '#2b7ab8', name: 'Disk %' },
  { key: METRIC_RAM, color: '#5cb85c', name: 'RAM %' },
]

export const LOCATION_METRIC_KEYS = [
  { key: METRIC_COLD_WATER_SHOCK, color: '#0ea5e9', name: 'Cold Water Shock Risk', chartType: 'bar' },
  { key: METRIC_WATER_TEMP, color: '#38bdf8', name: 'Water Temp (°C)', chartType: 'line' },
  { key: METRIC_ALERT_COUNT, color: '#f59e0b', name: 'Alert Count', chartType: 'bar' },
]

export const YOUTUBE_METRIC_KEYS = [
  { key: METRIC_TOTAL_STREAMS, color: '#e53935', name: 'Total Streams' },
  { key: METRIC_LIKE_COUNT, color: '#0d9488', name: 'Like Count' },
]

/** Vroom Vroom music video – opened in user's browser when emergency recovery is triggered */
export const VROOM_VROOM_VIDEO_URL = 'https://www.youtube.com/watch?v=qfAqtFuGjWM'
