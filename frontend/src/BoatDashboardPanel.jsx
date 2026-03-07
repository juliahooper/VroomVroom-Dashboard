import { useEffect, useState } from 'react'
import { fetchLatestSnapshot, fetchHistoricSnapshots, fetchThresholds, getMetric } from './api'
import {
  DEVICE_PC,
  DEVICE_YOUTUBE,
  deviceIdForLocation,
  METRIC_THREADS,
  METRIC_DISK,
  METRIC_RAM,
  METRIC_TOTAL_STREAMS,
  METRIC_LIKE_COUNT,
} from './constants'
import GaugeTachometer from './gauges/GaugeTachometer'
import GaugeSpeedometer from './gauges/GaugeSpeedometer'
import GaugeFuel from './gauges/GaugeFuel'
import HistoricCharts from './HistoricCharts'

const DEFAULT_THRESHOLDS = { thread_count: 300, ram_percent: 85, disk_usage_percent: 90, warning_fraction: 0.8 }

export default function BoatDashboardPanel({ view, onLiveData, selectedLocation }) {
  const [liveSnapshot, setLiveSnapshot] = useState(null)
  const [youtubeSnapshot, setYoutubeSnapshot] = useState(null)
  const [historicSnapshots, setHistoricSnapshots] = useState([])
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const historicDevice = selectedLocation ? deviceIdForLocation(selectedLocation.id) : DEVICE_PC

  useEffect(() => {
    let cancelled = false
    setError(null)
    function loadLive() {
      fetchLatestSnapshot(DEVICE_PC)
        .then((data) => { if (!cancelled) setLiveSnapshot(data) })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
      fetchLatestSnapshot(DEVICE_YOUTUBE)
        .then((data) => { if (!cancelled) setYoutubeSnapshot(data) })
        .catch(() => { if (!cancelled) setYoutubeSnapshot(null) })
    }
    function loadHistoric() {
      fetchHistoricSnapshots(historicDevice, 100)
        .then((data) => { if (!cancelled) setHistoricSnapshots(data) })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    if (view === 'live') {
      setLoading(true)
      fetchThresholds()
        .then((t) => { if (!cancelled) setThresholds(t) })
        .catch(() => {})
      loadLive()
      const t = setInterval(loadLive, 8000)
      return () => { cancelled = true; clearInterval(t) }
    } else {
      setLoading(true)
      loadHistoric()
      return () => { cancelled = true }
    }
  }, [view, historicDevice])

  if (view === 'historic') {
    return (
      <div className="boat-dashboard-panel boat-dashboard-panel--historic">
        <div className="boat-dashboard-panel__inner">
          {error && <div className="boat-dashboard-panel__error">{error}</div>}
          {loading && <div className="boat-dashboard-panel__loading">Loading history…</div>}
          {!loading && !error && (
            <HistoricCharts
              snapshots={historicSnapshots}
              isLocationView={!!selectedLocation}
              locationName={selectedLocation?.name}
            />
          )}
        </div>
      </div>
    )
  }

  const metrics = liveSnapshot?.metrics ?? []
  const threads = getMetric(metrics, METRIC_THREADS)
  const disk = getMetric(metrics, METRIC_DISK)
  const ram = getMetric(metrics, METRIC_RAM)
  const youtubeMetrics = youtubeSnapshot?.metrics ?? []
  const viewCount = getMetric(youtubeMetrics, METRIC_TOTAL_STREAMS)?.value ?? 0
  const likeCount = getMetric(youtubeMetrics, METRIC_LIKE_COUNT)?.value ?? 0

  const tc = thresholds.thread_count ?? 300
  const rc = thresholds.ram_percent ?? 85
  const dc = thresholds.disk_usage_percent ?? 90
  const wf = thresholds.warning_fraction ?? 0.8
  const threadWarning = Math.floor(tc * wf)
  const ramWarning = Math.floor(rc * wf)
  const diskWarning = Math.floor(dc * wf)

  useEffect(() => {
    if (view === 'live' && onLiveData) onLiveData({ likeCount, viewCount })
  }, [view, likeCount, viewCount, onLiveData])

  return (
    <div className="boat-dashboard-panel boat-dashboard-panel--live">
      <div className="boat-dashboard-panel__inner">
        {error && <div className="boat-dashboard-panel__error">{error}</div>}
        {loading && <div className="boat-dashboard-panel__loading">Loading…</div>}
        {!loading && !error && (
          <div className="boat-gauges-row">
            <div className="boat-gauge-wrap boat-gauge-wrap--left">
              <GaugeTachometer
                value={threads?.value ?? 0}
                dangerThreshold={tc}
                warningThreshold={threadWarning}
                max={Math.max(400, Math.ceil(tc * 1.2))}
                label="RPM"
                unit="threads"
              />
            </div>
            <div className="boat-gauge-wrap boat-gauge-wrap--center">
              <GaugeSpeedometer
                value={disk?.value ?? 0}
                dangerThreshold={dc}
                warningThreshold={diskWarning}
                max={Math.max(100, Math.ceil(dc * 1.2))}
                label="Disk"
                unit="%"
              />
            </div>
            <div className="boat-gauge-wrap boat-gauge-wrap--right">
              <GaugeFuel
                value={ram?.value ?? 0}
                dangerThreshold={rc}
                warningThreshold={ramWarning}
                max={100}
                label="Fuel"
                unit="%"
              />
            </div>
          </div>
        )}
        {!loading && !error && liveSnapshot && (
          <div className="boat-dashboard-panel__timestamp">
            Live: {new Date(liveSnapshot.timestamp_utc).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  )
}
