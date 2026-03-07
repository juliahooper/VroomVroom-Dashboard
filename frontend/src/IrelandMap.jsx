import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchLocations } from './api'

// Custom large, visible marker icon (default Leaflet markers are small and can be hard to see)
const MARKER_SIZE = 36
const createMarkerIcon = () =>
  L.divIcon({
    className: 'vroom-marker',
    html: `
      <div style="
        width: ${MARKER_SIZE}px;
        height: ${MARKER_SIZE}px;
        background: #dc2626;
        border: 3px solid #fff;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
      "></div>
    `,
    iconSize: [MARKER_SIZE, MARKER_SIZE],
    iconAnchor: [MARKER_SIZE / 2, MARKER_SIZE],
  })

const IRELAND_CENTER = [53.4, -7.7]
const IRELAND_ZOOM = 6

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
            icon={createMarkerIcon()}
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
