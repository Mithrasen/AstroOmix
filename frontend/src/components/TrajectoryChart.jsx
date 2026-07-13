import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export const MODEL_COLORS = {
  prophet: '#5aa9e6',
  arima: '#c9a227',
  lightgbm: '#e05c5c',
}

// Launch is mission day 0; splashdown is day 3. Shading the flight makes the
// 3-day window visible against the 289-day span, which is otherwise invisible.
const LAUNCH_DAY = 0
const RETURN_DAY = 3

export default function TrajectoryChart({ data }) {
  const { rows, models, lastObservedDay, yDomain, clipped } = useMemo(() => {
    const byDay = new Map()

    const touch = (day) => {
      if (!byDay.has(day)) byDay.set(day, { day })
      return byDay.get(day)
    }

    for (const [model, curve] of Object.entries(data.curves)) {
      for (const point of curve.points) {
        const row = touch(point.day)
        row[`${model}_yhat`] = point.yhat
        // Only carry a band when the model actually produced one. LightGBM's
        // bounds are null and must stay null — an Area fed [null, null] draws
        // nothing, which is the intent.
        if (curve.has_uncertainty && point.yhat_lower !== null) {
          row[`${model}_band`] = [point.yhat_lower, point.yhat_upper]
        }
      }
    }

    for (const point of data.observed) {
      touch(point.day).observed = point.value
    }

    const rows = [...byDay.values()].sort((a, b) => a.day - b.day)
    const lastObservedDay = Math.max(...data.observed.map((p) => p.day))
    const models = Object.keys(data.curves)

    // Scale the y-axis to the observations and the model *centre lines*, not to
    // the uncertainty bands. ARIMA's band is genuinely enormous at n=7 — it can
    // span negative cell counts — and letting it drive the domain squashes the
    // real data into an unreadable sliver.
    //
    // Consequence: wide bands get clipped at the top/bottom of the plot. A
    // clipped band looks narrower than it is, which would understate a model's
    // uncertainty, so we detect it and say so under the chart.
    const centres = []
    for (const row of rows) {
      for (const model of models) {
        if (typeof row[`${model}_yhat`] === 'number') centres.push(row[`${model}_yhat`])
      }
    }
    const observedValues = data.observed.map((p) => p.value)
    const all = [...centres, ...observedValues]
    const low = Math.min(...all)
    const high = Math.max(...all)
    const pad = (high - low || Math.abs(high) || 1) * 0.25
    const yDomain = [low - pad, high + pad]

    const clipped = models.filter((model) =>
      rows.some((row) => {
        const band = row[`${model}_band`]
        return band && (band[0] < yDomain[0] || band[1] > yDomain[1])
      }),
    )

    return { rows, models, lastObservedDay, yDomain, clipped }
  }, [data])

  return (
    <>
    <ResponsiveContainer width="100%" height={420}>
      <ComposedChart data={rows} margin={{ top: 8, right: 20, bottom: 26, left: 8 }}>
        <CartesianGrid stroke="#1d2431" />

        {/* The flight itself. */}
        <ReferenceArea
          x1={LAUNCH_DAY}
          x2={RETURN_DAY}
          fill="#5aa9e6"
          fillOpacity={0.12}
          label={{ value: 'flight', fill: '#8b96a8', fontSize: 10, position: 'insideTop' }}
        />
        {/* Everything right of this line is extrapolation — no data out there. */}
        <ReferenceLine
          x={lastObservedDay}
          stroke="#6b7688"
          strokeDasharray="4 4"
          label={{
            value: 'last draw (R+194)',
            fill: '#8b96a8',
            fontSize: 10,
            position: 'insideTopRight',
          }}
        />

        <XAxis
          type="number"
          dataKey="day"
          domain={['dataMin', 'dataMax']}
          stroke="#8b96a8"
          tick={{ fontSize: 11 }}
          label={{
            value: 'mission day (launch = 0, splashdown = 3)',
            position: 'insideBottom',
            offset: -12,
            fill: '#8b96a8',
            fontSize: 12,
          }}
        />
        <YAxis
          stroke="#8b96a8"
          tick={{ fontSize: 11 }}
          domain={yDomain}
          allowDataOverflow
          tickFormatter={(v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(1))}
          label={{
            value: data.unit,
            angle: -90,
            position: 'insideLeft',
            fill: '#8b96a8',
            fontSize: 11,
          }}
        />
        <Tooltip
          contentStyle={{
            background: '#0b0e14',
            border: '1px solid #232b39',
            borderRadius: 6,
            fontSize: 12,
          }}
          labelFormatter={(day) => `mission day ${day}`}
          formatter={(value, name) => {
            if (Array.isArray(value)) {
              return [`${value[0]?.toFixed(1)} – ${value[1]?.toFixed(1)}`, name]
            }
            return [typeof value === 'number' ? value.toFixed(1) : value, name]
          }}
        />
        {/* Top-aligned: at the bottom it collided with the x-axis title. */}
        <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />

        {/* Bands first, so lines and markers draw on top. */}
        {models.map((model) =>
          data.curves[model].has_uncertainty ? (
            <Area
              key={`${model}-band`}
              dataKey={`${model}_band`}
              name={`${model} 95% interval`}
              stroke="none"
              fill={MODEL_COLORS[model]}
              fillOpacity={0.13}
              isAnimationActive={false}
              connectNulls
              legendType="none"
            />
          ) : null,
        )}

        {models.map((model) => (
          <Line
            key={model}
            type="monotone"
            dataKey={`${model}_yhat`}
            name={model}
            stroke={MODEL_COLORS[model]}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}

        <Scatter
          dataKey="observed"
          name="observed"
          fill="#e6e9ef"
          shape="circle"
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>

    {clipped.length > 0 && (
      <div className="note" data-testid="clipped-note" style={{ color: '#d8b968' }}>
        The y-axis is scaled to the observations and model centre lines, so the{' '}
        {clipped.join(' and ')} interval{clipped.length > 1 ? 's are' : ' is'} clipped —
        it extends beyond the plotted range and is <em>wider</em> than it appears here.
        At n=7 that band can span physically impossible values (negative counts); that
        width is a real statement about how little the model knows, not a rendering
        artefact.
      </div>
    )}
    </>
  )
}
