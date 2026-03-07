import { useState } from 'react'
import './App.css'
import AlertCountBadge from './AlertCountBadge'
import BoatDashboardPanel from './BoatDashboardPanel'
import ColdWaterShockBadge from './ColdWaterShockBadge'
import IrelandMap from './IrelandMap'
import LikeCountBadge from './LikeCountBadge'
import ViewCountBadge from './ViewCountBadge'

export default function App() {
  const [view, setView] = useState('live')
  const [likeCount, setLikeCount] = useState(0)
  const [viewCount, setViewCount] = useState(0)
  const [selectedLocation, setSelectedLocation] = useState(null)

  const handleLiveData = (data) => {
    setLikeCount(data?.likeCount ?? 0)
    setViewCount(data?.viewCount ?? 0)
  }

  return (
    <div className="dashboard-container">
      <div className="dashboard-scroll-content">
        <img
          src={`${import.meta.env.BASE_URL}finalBackground.svg`}
          alt="Background"
          className="dashboard-bg"
        />
        {view === 'live' && (
          <div className="like-count-on-dashboard">
            <LikeCountBadge count={likeCount} />
            <ViewCountBadge count={viewCount} />
          </div>
        )}
        <section className="dashboard-map-section" aria-label="Location map and metrics">
          <div className="dashboard-map-section__map">
            <IrelandMap
              selectedLocationId={selectedLocation?.id}
              onSelectLocation={setSelectedLocation}
            />
          </div>
          <div className="dashboard-map-section__metrics">
            {selectedLocation ? (
              <>
                <ColdWaterShockBadge score={selectedLocation.cold_water_shock_risk_score ?? 0} />
                <AlertCountBadge count={selectedLocation.alert_count ?? 0} />
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
            )}
          </div>
        </section>
        <BoatDashboardPanel view={view} onLiveData={handleLiveData} />
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
    </div>
  )
}
