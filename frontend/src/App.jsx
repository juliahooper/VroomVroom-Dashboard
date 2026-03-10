import { useEffect, useState } from 'react'
import './App.css'
import { fetchLatestSnapshot, fetchHistoricSnapshots, getHistoricSinceIso, getMetric, sendCommand } from './api'
import { deviceIdForLocation, DEVICE_PC, DEVICE_YOUTUBE, METRIC_ALERT_COUNT, METRIC_COLD_WATER_SHOCK, METRIC_LIKE_COUNT, METRIC_TOTAL_STREAMS, METRIC_WATER_TEMP, VROOM_VROOM_VIDEO_URL } from './constants'
import AlertCountBadge from './AlertCountBadge'
import BoatDashboardPanel from './BoatDashboardPanel'
import DangerRecoveryModal from './DangerRecoveryModal'
import ColdWaterShockBadge from './ColdWaterShockBadge'
import HistoricCharts from './HistoricCharts'
import IrelandMapStatic from './IrelandMapStatic'
import LikeCountBadge from './LikeCountBadge'
import ViewCountBadge from './ViewCountBadge'
import { LOCATION_METRIC_KEYS, YOUTUBE_METRIC_KEYS } from './constants'

export default function App() {
  const [view, setView] = useState('live')
  const [likeCount, setLikeCount] = useState(0)
  const [viewCount, setViewCount] = useState(0)
  const [selectedLocation, setSelectedLocation] = useState(null)
  const [locationMetrics, setLocationMetrics] = useState(null)

  // YouTube: live badges (live view) or historic chart (historic view)
  const [youtubeHistoricSnapshots, setYoutubeHistoricSnapshots] = useState([])
  const [youtubeHistoricLoading, setYoutubeHistoricLoading] = useState(false)
  const [selectedYoutubeMetricKey, setSelectedYoutubeMetricKey] = useState(YOUTUBE_METRIC_KEYS[0]?.key ?? null)

  // Mobile/location: live badges (live view) or historic chart (historic view)
  const [locationHistoricSnapshots, setLocationHistoricSnapshots] = useState([])
  const [locationHistoricLoading, setLocationHistoricLoading] = useState(false)
  const [selectedLocationMetricKey, setSelectedLocationMetricKey] = useState(LOCATION_METRIC_KEYS[0]?.key ?? null)

  const [showDangerModal, setShowDangerModal] = useState(false)
  const [dangerSubmitting, setDangerSubmitting] = useState(false)

  const handleDanger = () => setShowDangerModal(true)
  const handleDangerCancel = () => setShowDangerModal(false)
  const handleDangerYes = () => {
    setDangerSubmitting(true)
    setShowDangerModal(false)
    window.open(VROOM_VROOM_VIDEO_URL, '_blank', 'noopener,noreferrer')
    sendCommand(DEVICE_PC, 'play_alert').catch((e) => console.error('Danger recovery failed:', e))
    setDangerSubmitting(false)
  }

  // Live: fetch latest for selected location (mobile metrics)
  useEffect(() => {
    if (!selectedLocation?.id || view !== 'live') {
      setLocationMetrics(null)
      return
    }
    const deviceId = deviceIdForLocation(selectedLocation.id)
    let cancelled = false
    fetchLatestSnapshot(deviceId)
      .then((snapshot) => {
        if (cancelled) return
        const metrics = snapshot?.metrics ?? []
        const risk = getMetric(metrics, METRIC_COLD_WATER_SHOCK)?.value ?? 0
        const alerts = getMetric(metrics, METRIC_ALERT_COUNT)?.value ?? 0
        setLocationMetrics({ cold_water_shock_risk_score: risk, alert_count: alerts })
      })
      .catch(() => { if (!cancelled) setLocationMetrics(null) })
    return () => { cancelled = true }
  }, [selectedLocation?.id, view])

  // Live: fetch YouTube for badges
  useEffect(() => {
    if (view !== 'live') return
    let cancelled = false
    function load() {
      fetchLatestSnapshot(DEVICE_YOUTUBE)
        .then((data) => {
          if (!cancelled && data) {
            const metrics = data?.metrics ?? []
            setLikeCount(getMetric(metrics, METRIC_LIKE_COUNT)?.value ?? 0)
            setViewCount(getMetric(metrics, METRIC_TOTAL_STREAMS)?.value ?? 0)
          }
        })
        .catch(() => {})
    }
    load()
    const t = setInterval(load, 8000)
    return () => { cancelled = true; clearInterval(t) }
  }, [view])

  // Historic: fetch YouTube snapshots for top-right chart
  useEffect(() => {
    if (view !== 'historic') return
    let cancelled = false
    setYoutubeHistoricLoading(true)
    fetchHistoricSnapshots(DEVICE_YOUTUBE, 100)
      .then((data) => { if (!cancelled) setYoutubeHistoricSnapshots(data) })
      .catch(() => { if (!cancelled) setYoutubeHistoricSnapshots([]) })
      .finally(() => { if (!cancelled) setYoutubeHistoricLoading(false) })
    return () => { cancelled = true }
  }, [view])

  // Historic: fetch location snapshots for metrics panel chart
  // Mobile: omit since filter so we get ALL available data (mobile data may be sparse or older than 7 days)
  // Mobile: filter to snapshots with valid location metrics (Cold Water Shock Risk, Water Temp)
  const LOCATION_METRIC_NAMES = [METRIC_COLD_WATER_SHOCK, METRIC_WATER_TEMP]
  const hasLocationMetrics = (snapshot) =>
    (snapshot?.metrics ?? []).some((m) => LOCATION_METRIC_NAMES.includes(m?.name))

  useEffect(() => {
    if (view !== 'historic' || !selectedLocation?.id) {
      setLocationHistoricSnapshots([])
      return
    }
    const deviceId = deviceIdForLocation(selectedLocation.id)
    let cancelled = false
    setLocationHistoricLoading(true)
    // Mobile: no since filter – get all snapshots (up to 500). PC/YouTube use 7-day filter.
    const since = deviceId?.startsWith('mobile:') ? undefined : getHistoricSinceIso()
    fetchHistoricSnapshots(deviceId, 500, since)
      .then((data) => {
        if (cancelled) return
        const valid = (data || []).filter(hasLocationMetrics)
        // Use only historic list (oldest-first from API reverse). Do not fall back to
        // latest snapshot — that made the chart show the most recent point as "historic".
        setLocationHistoricSnapshots(valid)
      })
      .catch(() => { if (!cancelled) setLocationHistoricSnapshots([]) })
      .finally(() => { if (!cancelled) setLocationHistoricLoading(false) })
    return () => { cancelled = true }
  }, [view, selectedLocation?.id])

  return (
    <div className="dashboard-container">
      <div className="dashboard-scroll-content">
        <img
          src={`${import.meta.env.BASE_URL}finalBackground.svg`}
          alt="Background"
          className="dashboard-bg"
        />
        <div className={`like-count-on-dashboard ${view === 'historic' ? 'like-count-on-dashboard--historic' : ''}`}>
          {view === 'live' ? (
            <>
              <LikeCountBadge count={likeCount} />
              <ViewCountBadge count={viewCount} />
            </>
          ) : (
            <div className="historic-chart-zone historic-chart-zone--youtube">
              {youtubeHistoricLoading && <div className="historic-chart-zone__loading">Loading…</div>}
              {!youtubeHistoricLoading && (
                <HistoricCharts
                  snapshots={youtubeHistoricSnapshots}
                  metricKeys={YOUTUBE_METRIC_KEYS}
                  selectedMetricKey={selectedYoutubeMetricKey}
                  onSelectMetric={setSelectedYoutubeMetricKey}
                  emptyMessage="No historic YouTube data yet."
                  chartId="youtube"
                  domain="auto"
                />
              )}
            </div>
          )}
        </div>
        <section className={`dashboard-map-section ${view === 'historic' ? 'dashboard-map-section--historic' : ''}`} aria-label="Location map and metrics">
          <div className="dashboard-map-section__map">
            <IrelandMapStatic
              selectedLocationId={selectedLocation?.id}
              onSelectLocation={setSelectedLocation}
            />
          </div>
          <div className="dashboard-map-section__metrics">
            {view === 'live' ? (
              selectedLocation ? (
                <>
                  <ColdWaterShockBadge score={locationMetrics?.cold_water_shock_risk_score ?? selectedLocation.cold_water_shock_risk_score ?? 0} />
                  <AlertCountBadge count={locationMetrics?.alert_count ?? selectedLocation.alert_count ?? 0} />
                  <div className="dashboard-map-section__location-name">
                    {selectedLocation.name}{selectedLocation.county ? `, ${selectedLocation.county}` : ''}
                  </div>
                </>
              ) : (
                <div className="dashboard-map-section__prompt">
                  <span className="dashboard-map-section__prompt-icon" aria-hidden>
                    <svg viewBox="0 0 24 24" fill="currentColor" width="32" height="32">
                      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
                    </svg>
                  </span>
                  <p>Select a location on the map</p>
                  <p className="dashboard-map-section__prompt-hint">Click a marker to see risk and alerts</p>
                </div>
              )
            ) : (
              <div className="historic-chart-zone historic-chart-zone--mobile">
                {!selectedLocation ? (
                  <div className="dashboard-map-section__prompt">
                    <span className="dashboard-map-section__prompt-icon" aria-hidden>
                      <svg viewBox="0 0 24 24" fill="currentColor" width="32" height="32">
                        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
                      </svg>
                    </span>
                    <p>Select a location on the map</p>
                    <p className="dashboard-map-section__prompt-hint">Click a marker to see historic metrics</p>
                  </div>
                ) : locationHistoricLoading ? (
                  <div className="historic-chart-zone__loading">Loading…</div>
                ) : (
                  <>
                    <div className="dashboard-map-section__location-name" style={{ marginBottom: 8 }}>
                      {selectedLocation.name}{selectedLocation.county ? `, ${selectedLocation.county}` : ''}
                    </div>
                    <HistoricCharts
                      snapshots={locationHistoricSnapshots}
                      metricKeys={LOCATION_METRIC_KEYS}
                      selectedMetricKey={selectedLocationMetricKey}
                      onSelectMetric={setSelectedLocationMetricKey}
                      emptyMessage={`No historic data for ${selectedLocation.name} yet.`}
                      chartId="mobile"
                      chartHeight={320}
                      domain="auto"
                    />
                  </>
                )}
              </div>
            )}
          </div>
        </section>
        <BoatDashboardPanel view={view} onDanger={handleDanger} />
      </div>
      <header className="dashboard-header" aria-label="View controls">
        <div className="dashboard-toggle" role="switch" aria-checked={view === 'historic'} aria-label="Toggle Live or Historic view">
          <button
            type="button"
            className="toggle-track"
            onClick={() => setView(view === 'live' ? 'historic' : 'live')}
          >
            <span className="toggle-labels">
              <span className={view === 'live' ? 'active' : ''}>Live</span>
              <span className={view === 'historic' ? 'active' : ''}>Historic</span>
            </span>
            <span className={`toggle-thumb ${view === 'historic' ? 'historic' : ''}`} />
          </button>
        </div>
      </header>
      {showDangerModal && (
        <DangerRecoveryModal
          onYes={handleDangerYes}
          onCancel={handleDangerCancel}
          isSubmitting={dangerSubmitting}
        />
      )}
    </div>
  )
}
