/**
 * Static Ireland map with positioned markers.
 * Uses Blank Ireland.svg (User:Angr, CC BY-SA 3.0, via Wikimedia Commons).
 * Lat/lng converted to % position for the 908×1159 viewBox.
 */
import { useEffect, useState } from 'react'
import { fetchLocations } from './api'

// Blank Ireland.svg: 908×1159, shape has ~3% padding. Map geographic bounds to shape area.
const IRELAND_BOUNDS = { latMin: 51.4, latMax: 55.4, lngMin: -10.5, lngMax: -6.0 }
const PADDING = { left: 2.5, right: 2.5, top: 2.5, bottom: 2.5 } // % padding in SVG

/** Convert lat/lng to percentage position on Blank Ireland.svg */
function latLngToPercent(lat, lng) {
  const xNorm = (lng - IRELAND_BOUNDS.lngMin) / (IRELAND_BOUNDS.lngMax - IRELAND_BOUNDS.lngMin)
  const yNorm = (IRELAND_BOUNDS.latMax - lat) / (IRELAND_BOUNDS.latMax - IRELAND_BOUNDS.latMin)
  const x = PADDING.left + xNorm * (100 - PADDING.left - PADDING.right)
  const y = PADDING.top + yNorm * (100 - PADDING.top - PADDING.bottom)
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
          title="Blank Ireland (User:Angr, CC BY-SA 3.0, via Wikimedia Commons)"
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
