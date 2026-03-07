import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix default marker icon in bundler (webpack/vite)
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
})

const IRELAND_CENTER = [53.4, -7.7]
const IRELAND_ZOOM = 6

// Use same origin by default; set VITE_API_BASE to backend URL when frontend is served elsewhere (e.g. VM).
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

function FitBounds({ locations }) {
  const map = useMap()
  useEffect(() => {
    if (!locations?.length) return
    const bounds = L.latLngBounds(locations.map(({ lat, lng }) => [lat, lng]))
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 10 })
  }, [map, locations])
  return null
}

export default function IrelandMap({ selectedLocationId, onSelectLocation }) {
  const [locations, setLocations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const url = `${API_BASE}/orm/locations`
    fetch(url)
      .then((res) => {
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error('Locations API not found (404). Ensure the backend is running and reachable.')
          }
          throw new Error(`HTTP ${res.status}`)
        }
        return res.json()
      })
      .then((data) => {
        if (!cancelled) setLocations(Array.isArray(data) ? data : [])
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
    <div className="ireland-map ireland-map--island">
      <MapContainer
        center={IRELAND_CENTER}
        zoom={IRELAND_ZOOM}
        className="ireland-map-container"
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {locations.length > 0 && <FitBounds locations={locations} />}
        {locations.map((loc) => (
          <Marker
            key={loc.id}
            position={[loc.lat, loc.lng]}
            eventHandlers={{
              click: () => typeof onSelectLocation === 'function' && onSelectLocation(loc),
            }}
          >
            <Popup>
              <strong>{loc.name}</strong>
              {loc.county && <><br />{loc.county}</>}
              {(loc.cold_water_shock_risk_score != null || loc.alert_count != null) && (
                <>
                  <br />
                  <small>Risk: {loc.cold_water_shock_risk_score ?? 0} · Alerts: {loc.alert_count ?? 0}</small>
                </>
              )}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
