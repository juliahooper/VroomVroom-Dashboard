import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'
import { useMemo } from 'react'
import { PC_METRIC_KEYS, LOCATION_METRIC_KEYS } from './constants'

function formatTime(utc) {
  try {
    const d = new Date(utc)
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return utc
  }
}

export default function HistoricCharts({ snapshots = [], isLocationView = false, locationName }) {
  const metricKeys = isLocationView ? LOCATION_METRIC_KEYS : PC_METRIC_KEYS

  const chartData = useMemo(() => {
    return snapshots.map((s) => {
      const point = { time: formatTime(s.timestamp_utc), full: s.timestamp_utc }
      for (const m of s.metrics || []) {
        point[m.name] = typeof m.value === 'number' ? m.value : null
      }
      return point
    })
  }, [snapshots])

  if (chartData.length === 0) {
    return (
      <div className="boat-charts-empty">
        <p>
          {isLocationView
            ? locationName
              ? `No historic data for ${locationName} yet.`
              : 'Select a location on the map to see its historic metrics.'
            : 'No historic data yet. Collect more snapshots to see trends.'}
        </p>
      </div>
    )
  }

  return (
    <div className="boat-charts">
      {isLocationView && locationName && (
        <h3 className="boat-chart-title" style={{ marginBottom: 16 }}>
          {locationName}
        </h3>
      )}
      {metricKeys.map(({ key, color, name }) => (
        <div key={key} className="boat-chart-card">
          <h3 className="boat-chart-title">{name}</h3>
          <ResponsiveContainer width="100%" height={140}>
            <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={'grad-' + key.replace(/\s/g, '')} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(10,77,122,0.15)" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="rgba(10,77,122,0.6)" />
              <YAxis tick={{ fontSize: 10 }} stroke="rgba(10,77,122,0.6)" width={32} />
              <Tooltip
                contentStyle={{ background: 'rgba(255,255,255,0.95)', borderRadius: 8, border: '1px solid rgba(10,77,122,0.2)' }}
                labelFormatter={(v) => v}
                formatter={(v) => [v != null ? Number(v).toFixed(2) : '—', name]}
              />
              <Area
                type="monotone"
                dataKey={key}
                stroke={color}
                strokeWidth={2}
                fill={'url(#grad-' + key.replace(/\s/g, '') + ')'}
                name={name}
                isAnimationActive
                animationDuration={400}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  )
}
