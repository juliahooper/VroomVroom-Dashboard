/**
 * Classic car-style fuel (RAM) gauge: dark face, 270° arc, orange needle.
 * Green / yellow / red zones from backend danger/warning thresholds (ram_percent).
 */
export default function GaugeFuel({
  value = 0,
  max = 100,
  dangerThreshold = 85,
  warningThreshold = 68,
  label = 'Fuel',
  unit = '%',
}) {
  const cx = 50
  const cy = 50
  const r = 40
  const needleLen = r - 6
  const scaleMax = Math.max(max, dangerThreshold, 1)
  const warn = Math.max(0, Number(warningThreshold) || 0)
  const danger = Math.max(warn, Number(dangerThreshold) || scaleMax)

  const pct = scaleMax > 0 ? Math.min(1, Math.max(0, value / scaleMax)) : 0
  const needleAngleDeg = 135 + pct * 270
  const needleRad = (needleAngleDeg * Math.PI) / 180
  const ex = cx + needleLen * Math.cos(needleRad)
  const ey = cy - needleLen * Math.sin(needleRad)

  const startAngle = 135
  const endAngle = 45
  const totalAngle = 270
  const greenAngle = totalAngle * (warn / scaleMax)
  const yellowAngle = totalAngle * ((danger - warn) / scaleMax)
  const redAngle = totalAngle * ((scaleMax - danger) / scaleMax)
  const rInner = r - 8
  const toRad = (deg) => (deg * Math.PI) / 180
  const point = (radius, deg) => {
    const rad = toRad(deg)
    return { x: cx + radius * Math.cos(rad), y: cy - radius * Math.sin(rad) }
  }
  /** Polygon-based arc segment (avoids SVG arc flags crossing 0°). Samples points clockwise from startDeg to endDeg. */
  const arcSegmentPath = (startDeg, endDeg) => {
    const clockwiseSpan = ((endDeg - startDeg + 360) % 360) || 360
    const steps = Math.max(2, Math.ceil(clockwiseSpan / 2))
    const degStep = clockwiseSpan / steps
    let path = `M ${point(r, startDeg).x} ${point(r, startDeg).y}`
    for (let i = 1; i <= steps; i++) {
      const d = startDeg + i * degStep
      path += ` L ${point(r, d).x} ${point(r, d).y}`
    }
    path += ` L ${point(rInner, endDeg).x} ${point(rInner, endDeg).y}`
    for (let i = 1; i <= steps; i++) {
      const d = endDeg - i * degStep
      path += ` L ${point(rInner, d).x} ${point(rInner, d).y}`
    }
    return path + ' Z'
  }
  const greenEndDeg = startAngle + greenAngle
  const yellowEndDeg = greenEndDeg + yellowAngle

  const tick = (position) => {
    const angleDeg = 135 + (position / 8) * 270
    const rad = (angleDeg * Math.PI) / 180
    const isMajor = Math.abs(position - Math.round(position)) < 0.01
    const inner = isMajor ? r - 5 : r - 3
    return {
      x1: cx + inner * Math.cos(rad),
      y1: cy - inner * Math.sin(rad),
      x2: cx + r * Math.cos(rad),
      y2: cy - r * Math.sin(rad),
    }
  }

  const majorTicks = [0, 1, 2, 3, 4, 5, 6, 7, 8]
  const minorTicks = []
  for (let i = 0; i < 8; i++) {
    for (let j = 1; j <= 4; j++) minorTicks.push(i + j * 0.2)
  }

  return (
    <div className="boat-gauge boat-gauge-fuel boat-gauge--classic">
      <div className="boat-gauge__face boat-gauge__face--dark">
        <div className="boat-gauge__dial">
          <svg viewBox="0 0 100 100" className="boat-gauge__svg" aria-hidden>
            <defs>
              <linearGradient id="fuel-face-shine" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#2a2a2a" />
                <stop offset="100%" stopColor="#0f0f0f" />
              </linearGradient>
              <clipPath id="clip-fuel">
                <circle cx={cx} cy={cy} r={r + 4} />
              </clipPath>
            </defs>
            <circle cx={cx} cy={cy} r={r + 3} fill="none" stroke="#3a3a3a" strokeWidth="2.5" />
            <circle cx={cx} cy={cy} r={r + 1} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
            <circle cx={cx} cy={cy} r={r} fill="url(#fuel-face-shine)" />
            <g clipPath="url(#clip-fuel)">
              <path d={arcSegmentPath(startAngle, greenEndDeg)} fill="#43a047" fillOpacity="1" />
              <path d={arcSegmentPath(greenEndDeg, yellowEndDeg)} fill="#ffeb3b" fillOpacity="1" />
              <path d={arcSegmentPath(yellowEndDeg, endAngle)} fill="#d32f2f" fillOpacity="1" />
            </g>
          {majorTicks.map((pos) => {
            const t = tick(pos)
            return <line key={'m' + pos} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} stroke="rgba(255,255,255,0.9)" strokeWidth="1.8" strokeLinecap="round" />
          })}
          {minorTicks.map((pos, i) => {
            const t = tick(pos)
            return <line key={'i' + i} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} stroke="rgba(255,255,255,0.5)" strokeWidth="1" strokeLinecap="round" />
          })}
          {majorTicks.map((num) => {
            const angleDeg = 135 + (num / 8) * 270
            const rad = (angleDeg * Math.PI) / 180
            const labelR = r - 14
            return (
              <text key={num} x={cx + labelR * Math.cos(rad)} y={cy - labelR * Math.sin(rad)} textAnchor="middle" dominantBaseline="middle" className="boat-gauge__number" fill="rgba(255,255,255,0.95)">{num}</text>
            )
          })}
          <text x={cx} y={cy - 6} textAnchor="middle" className="boat-gauge__center-label" fill="rgba(255,255,255,0.85)">{label}</text>
          <text x={cx} y={cy + 10} textAnchor="middle" className="boat-gauge__unit-label" fill="rgba(255,255,255,0.5)">{unit}</text>
          <line x1={cx} y1={cy} x2={ex} y2={ey} stroke="#ff9800" strokeWidth="2" strokeLinecap="round" style={{ transition: 'all 0.3s ease-out', filter: 'drop-shadow(0 0 1px rgba(0,0,0,0.5))' }} />
          <circle cx={cx} cy={cy} r="5" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
          </svg>
        </div>
        <div className="boat-gauge__value boat-gauge__value--dark">{Math.round(value)}{unit}</div>
      </div>
    </div>
  )
}
