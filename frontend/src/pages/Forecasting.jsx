import { useEffect, useState } from 'react'
import { getForecast, getForecastOptions } from '../api'
import TrajectoryChart, { MODEL_COLORS } from '../components/TrajectoryChart'

// Matches the backend's `le=365` on extra_days. Validated here too, so a bad
// value never becomes a 422 round-trip the user has to interpret.
const MAX_EXTRA_DAYS = 365
const MIN_EXTRA_DAYS = 0

function labelize(analyte) {
  return analyte.replace(/_/g, ' ')
}

function formatMetric(value, digits = 2) {
  return value === null || value === undefined ? '—' : value.toFixed(digits)
}

export default function Forecasting() {
  const [options, setOptions] = useState({ analytes: [], crew: [] })
  const [analyte, setAnalyte] = useState('absolute_neutrophils')
  const [crew, setCrew] = useState('mean')
  const [extraDays, setExtraDays] = useState(30)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getForecastOptions()
      .then(setOptions)
      .catch((e) => setError(`Could not load analyte list: ${e.message}`))
  }, [])

  const invalid =
    !Number.isInteger(extraDays) ||
    extraDays < MIN_EXTRA_DAYS ||
    extraDays > MAX_EXTRA_DAYS

  function submit(event) {
    event.preventDefault()
    if (invalid) return // client-side guard; never rely on the 422 round-trip

    setLoading(true)
    setError(null)
    getForecast(analyte, crew, extraDays)
      .then(setData)
      .catch((e) => setError(e.response?.data?.detail ?? e.message))
      .finally(() => setLoading(false))
  }

  // Fetch once on mount with the defaults, so the page is never an empty shell.
  useEffect(() => {
    submit({ preventDefault() {} })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const warning = data?.comparison?.best_by_mae_warning
  const best = data?.comparison?.best_by_mae

  return (
    <>
      <div className="panel">
        <form className="controls" onSubmit={submit}>
          <div>
            <label htmlFor="analyte">Analyte</label>
            <select
              id="analyte"
              value={analyte}
              onChange={(e) => setAnalyte(e.target.value)}
            >
              {options.analytes.map((a) => (
                <option key={a} value={a}>
                  {labelize(a)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="crew">Crew</label>
            <select id="crew" value={crew} onChange={(e) => setCrew(e.target.value)}>
              {options.crew.map((c) => (
                <option key={c} value={c}>
                  {c === 'mean' ? 'mean of 4 crew' : c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="extraDays">What-if: days past last draw</label>
            <input
              id="extraDays"
              type="number"
              min={MIN_EXTRA_DAYS}
              max={MAX_EXTRA_DAYS}
              value={extraDays}
              onChange={(e) => setExtraDays(Number.parseInt(e.target.value, 10))}
              style={{
                width: 90,
                background: 'var(--bg)',
                color: 'var(--text)',
                border: `1px solid ${invalid ? '#8b3a3a' : 'var(--border)'}`,
                borderRadius: 6,
                padding: '7px 10px',
                fontSize: 14,
              }}
            />
          </div>

          <button
            type="submit"
            disabled={invalid || loading}
            style={{
              background: invalid ? '#2a3140' : 'var(--accent)',
              color: invalid ? 'var(--muted)' : '#06131f',
              border: 'none',
              borderRadius: 6,
              padding: '8px 16px',
              fontSize: 14,
              fontWeight: 600,
              cursor: invalid || loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Fitting…' : 'Forecast'}
          </button>
        </form>

        {invalid && (
          <p className="note" style={{ color: '#f0a0a0' }} data-testid="validation-error">
            extra_days must be a whole number between {MIN_EXTRA_DAYS} and{' '}
            {MAX_EXTRA_DAYS}.
          </p>
        )}

        {data && (
          <p className="note" data-testid="caveat" style={{ marginTop: 12 }}>
            {data.caveat}
          </p>
        )}
      </div>

      {error && (
        <div className="panel error">
          <strong>Request failed.</strong> {error}
        </div>
      )}

      {data && !loading && (
        <>
          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 4px' }}>
              {labelize(data.analyte)}{' '}
              <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>
                — {data.crew === 'mean' ? 'mean of 4 crew' : data.crew},{' '}
                {data.n_timepoints} timepoints
              </span>
            </h2>
            <TrajectoryChart data={data} />
            <div className="note">
              Shaded bands are 95% prediction intervals. Anything right of the dashed
              line is extrapolation — there is no data out there.
            </div>
          </div>

          {/* The trap: LightGBM often wins LOO and cannot extrapolate at all.
              This must be impossible to miss, so it sits directly beside the
              best-model callout rather than in a tooltip or a footnote. */}
          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 14px' }}>
              Model comparison — leave-one-out CV
            </h2>

            <div
              data-testid="best-callout"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                marginBottom: warning ? 10 : 16,
              }}
            >
              <span className="muted" style={{ fontSize: 13 }}>
                Best by MAE:
              </span>
              <span
                style={{
                  fontWeight: 600,
                  fontSize: 15,
                  color: MODEL_COLORS[best] ?? 'var(--text)',
                }}
              >
                {best ?? '—'}
              </span>
            </div>

            {warning && (
              <div
                data-testid="best-warning"
                style={{
                  background: '#2a2113',
                  border: '1px solid #6b5424',
                  borderRadius: 8,
                  padding: '12px 14px',
                  marginBottom: 16,
                  fontSize: 13,
                  color: '#f0d9a0',
                }}
              >
                <strong>⚠ “Best” does not mean “best forecaster.”</strong>
                <div style={{ marginTop: 6 }}>{warning}</div>
              </div>
            )}

            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>MAPE %</th>
                  <th>Folds</th>
                  <th>Uncertainty</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.comparison.metrics).map(([model, m]) => (
                  <tr key={model} data-testid={`row-${model}`}>
                    <td style={{ color: MODEL_COLORS[model], fontWeight: 600 }}>
                      {model}
                      {model === best && (
                        <span className="muted" style={{ fontWeight: 400 }}>
                          {' '}
                          (best)
                        </span>
                      )}
                    </td>
                    <td>{formatMetric(m.mae)}</td>
                    <td>{formatMetric(m.rmse)}</td>
                    <td>{formatMetric(m.mape, 1)}</td>
                    <td>
                      {m.n_folds - m.n_failed}/{m.n_folds}
                    </td>
                    <td>
                      {data.curves[model]?.has_uncertainty ? (
                        '95% interval'
                      ) : (
                        <span className="muted" data-testid={`no-uncertainty-${model}`}>
                          no uncertainty estimate
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="note">
              LOO-CV holds out each of the {data.n_timepoints} timepoints once and fits
              on the rest. It measures how well a model <em>interpolates</em> the
              observed trajectory — it does <strong>not</strong> validate the what-if
              extrapolation below.
            </div>
          </div>

          {data.whatif && (
            <div className="panel">
              <h2 style={{ fontSize: 15, margin: '0 0 14px' }}>
                What-if: {extraDays} days past the last draw
              </h2>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                  gap: 14,
                }}
              >
                {Object.entries(data.whatif).map(([model, w]) => (
                  <div
                    key={model}
                    data-testid={`whatif-${model}`}
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      padding: 14,
                    }}
                  >
                    <div
                      style={{
                        color: MODEL_COLORS[model],
                        fontWeight: 600,
                        fontSize: 13,
                        marginBottom: 6,
                      }}
                    >
                      {model} · mission day {w.day}
                    </div>

                    <div style={{ fontSize: 22, fontWeight: 600 }}>
                      {w.yhat === null ? '—' : w.yhat.toFixed(1)}{' '}
                      <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                        {data.unit}
                      </span>
                    </div>

                    <div className="note" style={{ marginTop: 4 }}>
                      {w.yhat_lower !== null && w.yhat_upper !== null ? (
                        <>
                          95% interval: {w.yhat_lower.toFixed(1)} –{' '}
                          {w.yhat_upper.toFixed(1)}
                        </>
                      ) : (
                        <span data-testid={`whatif-no-band-${model}`}>
                          no uncertainty estimate
                        </span>
                      )}
                    </div>

                    {w.flat_extrapolation && (
                      <div
                        data-testid={`flat-${model}`}
                        style={{
                          marginTop: 10,
                          background: '#2a1a1a',
                          border: '1px solid #6b2d2d',
                          borderRadius: 6,
                          padding: '8px 10px',
                          fontSize: 12,
                          color: '#f0a0a0',
                        }}
                      >
                        <strong>⚠ Not a projection.</strong> {w.caveat}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </>
  )
}
