/**
 * Badge for number of alerts: alert/warning icon, same bubble style as Like/View.
 */
export default function AlertCountBadge({ count = 0 }) {
  const value = Number(count)
  return (
    <div className="location-metric-badge alert-count-badge" aria-label={`Alerts: ${value}`}>
      <div className="location-metric-badge__bubble">
        <span className="location-metric-badge__icon alert-count-badge__icon" aria-hidden>
          <svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22">
            <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
          </svg>
        </span>
        <span className="location-metric-badge__number">{value}</span>
      </div>
      <div className="location-metric-badge__label">Number of alerts</div>
    </div>
  )
}
