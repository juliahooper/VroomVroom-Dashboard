import { useEffect, useRef, useState } from 'react'
import { fetchLatestSnapshot, fetchHistoricSnapshots, fetchThresholds, getMetric } from './api'
import {
  DEVICE_PC,
  METRIC_THREADS,
  METRIC_DISK,
  METRIC_RAM,
} from './constants'

/** Map metric name → config threshold key (for frontend danger check) */
const METRIC_TO_THRESHOLD = {
  [METRIC_THREADS]: 'thread_count',
  [METRIC_RAM]: 'ram_percent',
  [METRIC_DISK]: 'disk_usage_percent',
}
import GaugeTachometer from './gauges/GaugeTachometer'
import GaugeSpeedometer from './gauges/GaugeSpeedometer'
import GaugeFuel from './gauges/GaugeFuel'
import HistoricCharts from './HistoricCharts'
import { PC_METRIC_KEYS } from './constants'

const DEFAULT_THRESHOLDS = { thread_count: 300, ram_percent: 85, disk_usage_percent: 90, warning_fraction: 0.8 }
/** Lower thresholds for danger popup when API fails – ensures popup still shows for clearly dangerous values */
const POPUP_FALLBACK_THRESHOLDS = { thread_count: 100, ram_percent: 80, disk_usage_percent: 85, warning_fraction: 0.8 }

export default function BoatDashboardPanel({ view, onDanger }) {
  const [liveSnapshot, setLiveSnapshot] = useState(null)
  const [historicSnapshots, setHistoricSnapshots] = useState([])
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedMetricKey, setSelectedMetricKey] = useState(PC_METRIC_KEYS[0]?.key ?? null)
  const dangerReportedRef = useRef(false)
  const thresholdsRef = useRef(DEFAULT_THRESHOLDS)

  useEffect(() => {
    let cancelled = false
    setError(null)
    function loadLive() {
      const t = thresholdsRef.current
      fetchLatestSnapshot(DEVICE_PC)
        .then((data) => {
          if (!cancelled) {
            setLiveSnapshot(data)
            const metrics = data?.metrics ?? []
            const hasDangerFromStatus = metrics.some((m) => m.status === 'danger')
            const hasDangerFromValues = metrics.some((m) => {
              const key = METRIC_TO_THRESHOLD[m?.name]
              const limit = key ? t[key] : null
              return limit != null && typeof m?.value === 'number' && m.value >= limit
            })
            const hasDanger = hasDangerFromStatus || hasDangerFromValues
            if (hasDanger && !dangerReportedRef.current && onDanger) {
              dangerReportedRef.current = true
              onDanger(data)
            }
            if (!hasDanger) dangerReportedRef.current = false
          }
        })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    function loadHistoric() {
      fetchHistoricSnapshots(DEVICE_PC, 100)
        .then((data) => { if (!cancelled) setHistoricSnapshots(data) })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    if (view === 'live') {
      dangerReportedRef.current = false
      setLoading(true)
      fetchThresholds()
        .then((t) => {
          if (!cancelled) {
            setThresholds(t)
            thresholdsRef.current = t
          }
          loadLive()
        })
        .catch(() => {
          if (!cancelled) thresholdsRef.current = POPUP_FALLBACK_THRESHOLDS
          loadLive()
        })
      const t = setInterval(() => loadLive(), 8000)
      return () => { cancelled = true; clearInterval(t) }
    } else {
      dangerReportedRef.current = false
      setLoading(true)
      loadHistoric()
      return () => { cancelled = true }
    }
  }, [view, onDanger])

  if (view === 'historic') {
    return (
      <div className="boat-dashboard-panel boat-dashboard-panel--historic">
        <div className="boat-dashboard-panel__inner">
          {error && <div className="boat-dashboard-panel__error">{error}</div>}
          {loading && <div className="boat-dashboard-panel__loading">Loading history…</div>}
          {!loading && !error && (
            <HistoricCharts
              snapshots={historicSnapshots}
              metricKeys={PC_METRIC_KEYS}
              selectedMetricKey={selectedMetricKey}
              onSelectMetric={setSelectedMetricKey}
              emptyMessage="No historic PC data yet. Collect more snapshots to see trends."
              chartId="pc"
              chartHeight={420}
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

  const tc = thresholds.thread_count ?? 300
  const rc = thresholds.ram_percent ?? 85
  const dc = thresholds.disk_usage_percent ?? 90
  const wf = thresholds.warning_fraction ?? 0.8
  const threadWarning = Math.floor(tc * wf)
  const ramWarning = Math.floor(rc * wf)
  const diskWarning = Math.floor(dc * wf)

  return (
    <div className="boat-dashboard-panel boat-dashboard-panel--live">
      <div className="boat-dashboard-panel__inner">
        {error && <div className="boat-dashboard-panel__error">{error}</div>}
        {loading && <div className="boat-dashboard-panel__loading">Loading…</div>}
        {!loading && !error && (
          <div className="boat-gauges-layout">
            <div className="boat-gauges-row">
              <div className="boat-gauge-wrap boat-gauge-wrap--left boat-gauge-wrap--large">
                <GaugeTachometer
                  value={threads?.value ?? 0}
                  dangerThreshold={tc}
                  warningThreshold={threadWarning}
                  max={Math.max(400, Math.ceil(tc * 1.2))}
                  label="Processes"
                  unit="threads"
                />
              </div>
              <div className="boat-gauge-wrap boat-gauge-wrap--center boat-gauge-wrap--large">
                <GaugeFuel
                  value={ram?.value ?? 0}
                  dangerThreshold={rc}
                  warningThreshold={ramWarning}
                  max={100}
                  label={METRIC_RAM}
                  unit="%"
                />
              </div>
              <div className="boat-gauge-wrap boat-gauge-wrap--right boat-gauge-wrap--large">
                <GaugeSpeedometer
                  value={disk?.value ?? 0}
                  dangerThreshold={dc}
                  warningThreshold={diskWarning}
                  max={Math.max(100, Math.ceil(dc * 1.2))}
                  label={METRIC_DISK}
                  unit="%"
                />
              </div>
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
