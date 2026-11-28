/**
 * Dependency-free SVG charts for report results (F1).
 *
 * The app has no chart library, so these primitives render plain SVG with a
 * fixed viewBox and scale to their container. They are intentionally pure:
 * data preparation happens in the caller, which keeps them reusable for the
 * report result panel and any future dashboard cards.
 */
import React from 'react'

export type ReportChartType = 'bar' | 'donut' | 'line'

interface ChartProps {
  labels: string[]
  values: number[]
  title?: string
}

interface ReportChartProps extends ChartProps {
  type: ReportChartType
}

const COLORS = [
  '#2c3e50', '#2980b9', '#27ae60', '#e67e22', '#8e44ad',
  '#16a085', '#c0392b', '#7f8c8d', '#f39c12', '#3498db'
]

const WIDTH = 640
const HEIGHT = 300
const PLOT_LEFT = 60
const PLOT_RIGHT = 620
const PLOT_TOP = 24
const PLOT_BOTTOM = 250
const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP

const shortLabel = (value: string, max = 16): string =>
  value.length > max ? `${value.slice(0, max - 1)}…` : value

const formatValue = (value: number): string =>
  Number.isInteger(value) ? String(value) : value.toFixed(2)

const ChartFrame: React.FC<{
  title: string
  children: React.ReactNode
}> = ({ title, children }) => (
  <div className="report-chart" role="img" aria-label={title}>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMidYMid meet">
      <title>{title}</title>
      {children}
    </svg>
  </div>
)

const GridLines: React.FC<{ max: number; min?: number }> = ({ max, min = 0 }) => (
  <>
    {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
      const y = PLOT_BOTTOM - fraction * PLOT_HEIGHT
      const value = min + fraction * (max - min)
      return (
        <g key={fraction}>
          <line className="chart-grid-line" x1={PLOT_LEFT} y1={y} x2={PLOT_RIGHT} y2={y} />
          <text className="chart-axis-label" x={PLOT_LEFT - 8} y={y + 4} textAnchor="end">
            {formatValue(value)}
          </text>
        </g>
      )
    })}
  </>
)

const BarChart: React.FC<ChartProps> = ({ labels, values, title }) => {
  const magnitude = Math.max(...values.map((value) => Math.abs(value)), 1)
  const slot = (PLOT_RIGHT - PLOT_LEFT) / values.length
  const barWidth = Math.max(4, Math.min(48, slot * 0.65))
  const rotate = values.length > 8

  return (
    <ChartFrame title={title || 'Bar chart'}>
      <GridLines max={magnitude} min={0} />
      {values.map((value, index) => {
        const height = (Math.abs(value) / magnitude) * PLOT_HEIGHT
        const x = PLOT_LEFT + index * slot + (slot - barWidth) / 2
        const y = value < 0 ? PLOT_BOTTOM : PLOT_BOTTOM - height
        const labelX = x + barWidth / 2
        return (
          <g key={`${labels[index]}-${index}`}>
            <rect
              className="chart-bar"
              x={x}
              y={y}
              width={barWidth}
              height={Math.max(height, 1)}
              fill={COLORS[index % COLORS.length]}
              rx={2}
            >
              <title>{`${labels[index]}: ${formatValue(value)}`}</title>
            </rect>
            <text
              className="chart-label"
              x={labelX}
              y={PLOT_BOTTOM + 20}
              textAnchor={rotate ? 'end' : 'middle'}
              transform={rotate ? `rotate(-40 ${labelX} ${PLOT_BOTTOM + 20})` : undefined}
            >
              {shortLabel(labels[index])}
            </text>
          </g>
        )
      })}
    </ChartFrame>
  )
}

const LineChart: React.FC<ChartProps> = ({ labels, values, title }) => {
  const max = Math.max(...values)
  const min = Math.min(...values)
  const span = max - min || 1
  const step = values.length > 1 ? (PLOT_RIGHT - PLOT_LEFT) / (values.length - 1) : 0
  const points = values.map((value, index) => [
    PLOT_LEFT + index * step,
    PLOT_BOTTOM - ((value - min) / span) * PLOT_HEIGHT,
  ])
  const path = points.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `${PLOT_LEFT},${PLOT_BOTTOM} ${path} ${PLOT_LEFT + (points.length - 1) * step},${PLOT_BOTTOM}`

  return (
    <ChartFrame title={title || 'Line chart'}>
      <GridLines max={max} min={min} />
      {points.length > 1 && <polygon className="chart-area" points={area} />}
      {points.length > 1 && <polyline className="chart-line" points={path} />}
      {points.map(([x, y], index) => (
        <g key={`${labels[index]}-${index}`}>
          <circle className="chart-point" cx={x} cy={y} r={4} fill={COLORS[index % COLORS.length]}>
            <title>{`${labels[index]}: ${formatValue(values[index])}`}</title>
          </circle>
          <text className="chart-label" x={x} y={PLOT_BOTTOM + 20} textAnchor="middle">
            {shortLabel(labels[index], values.length > 8 ? 6 : 16)}
          </text>
        </g>
      ))}
    </ChartFrame>
  )
}

const DonutChart: React.FC<ChartProps> = ({ labels, values, title }) => {
  const total = values.reduce((sum, value) => sum + Math.max(value, 0), 0)
  const radius = 72
  const circumference = 2 * Math.PI * radius
  let offset = 0

  return (
    <div className="report-chart-block">
      <ChartFrame title={title || 'Donut chart'}>
        <circle className="chart-donut-track" cx={170} cy={150} r={radius} />
        {total > 0 && values.map((value, index) => {
          const fraction = Math.max(value, 0) / total
          const length = fraction * circumference
          const segment = (
            <circle
              key={`${labels[index]}-${index}`}
              cx={170}
              cy={150}
              r={radius}
              fill="none"
              stroke={COLORS[index % COLORS.length]}
              strokeWidth={34}
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 170 150)"
            >
              <title>{`${labels[index]}: ${formatValue(value)}`}</title>
            </circle>
          )
          offset += length
          return segment
        })}
        <text className="chart-donut-total" x={170} y={146} textAnchor="middle">
          {formatValue(total)}
        </text>
        <text className="chart-axis-label" x={170} y={168} textAnchor="middle">
          total
        </text>
      </ChartFrame>
      <ul className="chart-legend">
        {labels.map((label, index) => (
          <li key={`${label}-${index}`} className="chart-legend-item">
            <span className="chart-swatch" style={{ background: COLORS[index % COLORS.length] }} />
            <span>{shortLabel(label, 28)}</span>
            <strong>{formatValue(values[index])}</strong>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Renders one of three chart types from parallel label/value arrays.
 * Callers are responsible for aggregation so the same data can also be shown
 * in the results table.
 */
export const ReportCharts: React.FC<ReportChartProps> = ({ type, labels, values, title }) => {
  if (!labels.length || !values.length) {
    return <div className="chart-empty">No data available for this chart.</div>
  }

  if (type === 'donut') {
    return <DonutChart labels={labels} values={values} title={title} />
  }
  if (type === 'line') {
    return <LineChart labels={labels} values={values} title={title} />
  }
  return <BarChart labels={labels} values={values} title={title} />
}
