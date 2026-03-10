import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Bar,
  BarChart,
} from 'recharts'
import { useMemo } from 'react'

function formatTime(utc) {
  try {
    const d = new Date(utc)
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return utc
  }
}

function formatDateTime(utc) {
  try {
    const d = new Date(utc)
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return utc
  }
}

export default function HistoricCharts({
  snapshots = [],
  metricKeys = [],
  selectedMetricKey,
  onSelectMetric,
  emptyMessage = 'No historic data yet. Collect more snapshots to see trends.',
  chartId = 'chart',
  chartHeight = 140,
  domain = undefined,
}) {
  const chartData = useMemo(() => {
    const first = snapshots[0]?.timestamp_utc
    const last = snapshots[snapshots.length - 1]?.timestamp_utc
    const spansMultipleDays = first && last && (new Date(last) - new Date(first)) > 24 * 60 * 60 * 1000
    const labelFn = spansMultipleDays ? formatDateTime : formatTime

    // Map API metric names to chart keys (handles "Water Temp" vs "Water Temp (°C)" etc.)
    const nameToKey = {
      'Water Temp': 'Water Temp',
      'Water Temp (°C)': 'Water Temp',
      'Cold Water Shock Risk': 'Cold Water Shock Risk',
      'Cold Water Shock Risk (%)': 'Cold Water Shock Risk',
    }

    return snapshots.map((s) => {
      const point = {
        time: formatTime(s.timestamp_utc),
        timeLabel: formatDateTime(s.timestamp_utc),
        label: labelFn(s.timestamp_utc),
        full: s.timestamp_utc,
      }
      for (const m of s.metrics || []) {
        const val = typeof m.value === 'number' ? m.value : null
        point[m.name] = val
        const chartKey = nameToKey[m.name]
        if (chartKey && metricKeys.some((mk) => mk.key === chartKey)) {
          point[chartKey] = val
        }
      }
      return point
    })
  }, [snapshots, metricKeys])

  const activeKey = selectedMetricKey ?? (metricKeys[0]?.key ?? null)
  const activeMetric = metricKeys.find((m) => m.key === activeKey) ?? metricKeys[0]

  if (chartData.length === 0) {
    return (
      <div className="boat-charts-empty">
        <p>{emptyMessage}</p>
      </div>
    )
  }

  if (metricKeys.length === 0) {
    return (
      <div className="boat-charts-empty">
        <p>{emptyMessage}</p>
      </div>
    )
  }

  const gradientId = 'grad-' + chartId + '-' + (activeMetric?.key ?? '').replace(/\s/g, '')
  const useBarChart = activeMetric?.chartType === 'bar'
  const color = activeMetric?.color ?? '#0a4d7a'
  const margin = { top: 8, right: 8, left: 16, bottom: 0 }
  const minChartWidth = Math.max(400, chartData.length * 12)
  const gridProps = { strokeDasharray: '3 3', stroke: 'rgba(10,77,122,0.15)' }
  const axisProps = { tick: { fontSize: 10 }, stroke: 'rgba(10,77,122,0.6)' }
  const yDomain = domain === 'auto' ? ['auto', 'auto'] : undefined
  const tooltipProps = {
    contentStyle: { background: 'rgba(255,255,255,0.95)', borderRadius: 8, border: '1px solid rgba(10,77,122,0.2)' },
    labelFormatter: (v) => v,
    formatter: (v) => [v != null ? Number(v).toFixed(2) : '—', activeMetric?.name ?? activeKey],
  }

  return (
    <div className="boat-charts boat-charts--single">
      <div className="boat-chart-toggle" role="tablist" aria-label="Metric selection">
        {metricKeys.map(({ key, name }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={key === activeKey}
            className={`boat-chart-toggle__tab ${key === activeKey ? 'boat-chart-toggle__tab--active' : ''}`}
            onClick={() => onSelectMetric?.(key)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="boat-chart-card">
        <h3 className="boat-chart-title">{activeMetric?.name ?? activeKey}</h3>
        <div className="boat-chart-scroll-wrap">
          <div className="boat-chart-inner" style={{ minWidth: minChartWidth }}>
            <ResponsiveContainer width="100%" height={chartHeight}>
              {useBarChart ? (
                <BarChart data={chartData} margin={margin} barCategoryGap="4%">
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} width={60} domain={yDomain} />
                  <Tooltip {...tooltipProps} />
              <Bar
                dataKey={activeKey}
                fill={color}
                name={activeMetric?.name ?? activeKey}
                isAnimationActive
                animationDuration={400}
              />
            </BarChart>
          ) : (
            <AreaChart data={chartData} margin={margin}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
              <YAxis {...axisProps} width={60} domain={yDomain} />
              <Tooltip {...tooltipProps} />
              <Area
                type="monotone"
                dataKey={activeKey}
                stroke={color}
                strokeWidth={2}
                fill={'url(#' + gradientId + ')'}
                name={activeMetric?.name ?? activeKey}
                isAnimationActive
                animationDuration={400}
              />
            </AreaChart>
          )}
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}
