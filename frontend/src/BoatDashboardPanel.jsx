import { useEffect, useState } from 'react'
import { fetchLatestSnapshot, fetchHistoricSnapshots, fetchThresholds, getMetric } from './api'
import GaugeTachometer from './gauges/GaugeTachometer'
import GaugeSpeedometer from './gauges/GaugeSpeedometer'
import GaugeFuel from './gauges/GaugeFuel'
import HistoricCharts from './HistoricCharts'

const DEVICE = 'pc-01'
const DEFAULT_THRESHOLDS = { thread_count: 300, ram_percent: 85, disk_read_mb_s: 50, warning_fraction: 0.8 }

export default function BoatDashboardPanel({ view, onLiveData }) {
  const [liveSnapshot, setLiveSnapshot] = useState(null)
  const [historicSnapshots, setHistoricSnapshots] = useState([])
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    function loadLive() {
      fetchLatestSnapshot(DEVICE)
        .then((data) => { if (!cancelled) setLiveSnapshot(data) })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    function loadHistoric() {
      fetchHistoricSnapshots(DEVICE, 100)
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
  }, [view])

  if (view === 'historic') {
    return (
      <div className="boat-dashboard-panel boat-dashboard-panel--historic">
        <div className="boat-dashboard-panel__inner">
          {error && <div className="boat-dashboard-panel__error">{error}</div>}
          {loading && <div className="boat-dashboard-panel__loading">Loading history…</div>}
          {!loading && !error && <HistoricCharts snapshots={historicSnapshots} />}
        </div>
      </div>
    )
  }

  const metrics = liveSnapshot?.metrics ?? []
  const threads = getMetric(metrics, 'Running Threads')
  const disk = getMetric(metrics, 'Disk Read Speed')
  const ram = getMetric(metrics, 'RAM Usage')
  const likeMetric = getMetric(metrics, 'total_streams')
  const likeCount = likeMetric?.value ?? 0
  const viewCount = likeMetric?.value ?? 0

  const tc = thresholds.thread_count ?? 300
  const rc = thresholds.ram_percent ?? 85
  const dc = thresholds.disk_read_mb_s ?? 50
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
                max={Math.max(80, Math.ceil(dc * 1.2))}
                label="Speed"
                unit="MB/s"
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
