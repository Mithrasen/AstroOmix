import { useEffect, useState } from 'react'
import { getAbtest, getStudies } from '../api'
import HitsTable from '../components/HitsTable'
import VolcanoPlot from '../components/VolcanoPlot'

export default function ABTesting() {
  const [studies, setStudies] = useState([])
  const [accession, setAccession] = useState('OSD-104')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies()
      .then((all) => setStudies(all.filter((s) => s.module === 'abtest')))
      .catch((e) => setError(`Could not load studies: ${e.message}`))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    getAbtest(accession)
      .then((result) => {
        // Guard against a slow earlier request landing after a newer one and
        // overwriting the current selection's results.
        if (!cancelled) setData(result)
      })
      .catch((e) => {
        if (!cancelled) setError(e.response?.data?.detail ?? e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [accession])

  const study = studies.find((s) => s.accession === accession)

  return (
    <>
      <div className="panel">
        <div className="controls">
          <div>
            <label htmlFor="accession">Dataset</label>
            <select
              id="accession"
              value={accession}
              onChange={(event) => setAccession(event.target.value)}
            >
              {(studies.length ? studies : [{ accession: 'OSD-104', label: 'OSD-104' }]).map(
                (s) => (
                  <option key={s.accession} value={s.accession}>
                    {s.accession} — {s.tissue ?? s.label}
                  </option>
                ),
              )}
            </select>
          </div>
          {loading && <span className="muted">Running DESeq2… (~15s on a cold cache)</span>}
        </div>

        {study && (
          <p className="note" style={{ marginTop: 12 }}>
            {study.design} · {study.assay} · {study.notes}
          </p>
        )}

        {data && !loading && (
          <div className="stats">
            <div className="stat">
              <div className="value">{data.n_genes.toLocaleString()}</div>
              <div className="label">genes tested</div>
            </div>
            <div className="stat">
              <div className="value">{data.n_significant.toLocaleString()}</div>
              <div className="label">FDR &lt; 0.05</div>
            </div>
            <div className="stat">
              <div className="value">{data.method}</div>
              <div className="label">{data.contrast}</div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="panel error">
          <strong>Request failed.</strong> {error}
          <div className="note" style={{ color: 'inherit' }}>
            Is the backend running? <code>uvicorn main:app --reload --port 8000</code>{' '}
            from <code>backend/</code>.
          </div>
        </div>
      )}

      {data && !loading && (
        <>
          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 14px' }}>Volcano</h2>
            <VolcanoPlot results={data.results} />
          </div>
          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 14px' }}>Hits</h2>
            <HitsTable results={data.results} />
          </div>
        </>
      )}
    </>
  )
}
