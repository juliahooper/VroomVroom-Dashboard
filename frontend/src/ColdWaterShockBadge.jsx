/**
 * Badge for cold water shock risk score: thermometer + snowflake, same bubble style as Like/View.
 * score: 0–100.
 */
export default function ColdWaterShockBadge({ score = 0 }) {
  const value = Number(score)
  return (
    <div className="location-metric-badge cold-water-shock-badge" aria-label={`Cold water shock risk: ${value}`}>
      <div className="location-metric-badge__bubble">
        <span className="location-metric-badge__icon cold-water-shock-badge__icon" aria-hidden>
          <svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22">
            <path d="M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-8c.55 0 1 .45 1 1v1h-2V6c0-.55.45-1 1-1z" />
          </svg>
        </span>
        <span className="location-metric-badge__snowflake" aria-hidden>
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
            <path d="M12 0l1.5 4.5L18 3l-1.5 4.5L21 9l-4.5 1.5L18 15l-4.5-1.5L12 18l-1.5-4.5L6 15l1.5-4.5L3 9l4.5-1.5L6 3l4.5 1.5L12 0z" />
          </svg>
        </span>
        <span className="location-metric-badge__number">{value}</span>
      </div>
      <div className="location-metric-badge__label">Cold water shock risk</div>
    </div>
  )
}
