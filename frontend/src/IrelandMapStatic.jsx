/**
 * Static Ireland map with positioned markers.
 * Uses a static image + percentage positioning instead of Leaflet.
 * Simpler and more reliable for marker visibility.
 */
import { useEffect, useState } from 'react'
import { fetchLocations } from './api'

// Ireland bounding box (lat/lng)
const IRELAND_BOUNDS = {
  latMin: 51.4,
  latMax: 55.4,
  lngMin: -10.5,
  lngMax: -6.0,
}

/** Convert lat/lng to percentage position (0-100) on the map image */
function latLngToPercent(lat, lng) {
  const x = ((lng - IRELAND_BOUNDS.lngMin) / (IRELAND_BOUNDS.lngMax - IRELAND_BOUNDS.lngMin)) * 100
  const y = ((IRELAND_BOUNDS.latMax - lat) / (IRELAND_BOUNDS.latMax - IRELAND_BOUNDS.latMin)) * 100
  return { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) }
}

export default function IrelandMapStatic({ selectedLocationId, onSelectLocation }) {
  const [locations, setLocations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchLocations()
      .then((data) => {
        if (!cancelled) setLocations(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  if (loading) return <div className="ireland-map ireland-map--loading">Loading map…</div>
  if (error) {
    return (
      <div className="ireland-map ireland-map--error">
        <span className="ireland-map--error__title">Map unavailable</span>
        <span className="ireland-map--error__detail">{error}</span>
      </div>
    )
  }

  return (
    <div className="ireland-map ireland-map--island ireland-map--static">
      <div className="ireland-map-static__container">
        <img
          src={`${import.meta.env.BASE_URL}ireland-map.svg`}
          alt="Map of Ireland"
          className="ireland-map-static__image"
        />
        {locations.map((loc) => {
          const pos = latLngToPercent(loc.lat, loc.lng)
          const isSelected = selectedLocationId === loc.id
          return (
            <button
              key={loc.id}
              type="button"
              className={`ireland-map-static__marker ${isSelected ? 'ireland-map-static__marker--selected' : ''}`}
              style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              onClick={() => typeof onSelectLocation === 'function' && onSelectLocation(loc)}
              title={`${loc.name}${loc.county ? `, ${loc.county}` : ''}`}
              aria-label={`${loc.name} - Risk: ${loc.cold_water_shock_risk_score ?? 0}, Alerts: ${loc.alert_count ?? 0}`}
            >
              <span className="ireland-map-static__marker-pin" />
            </button>
          )
        })}
      </div>
    </div>
  )
}
